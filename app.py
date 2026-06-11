"""
智能出题系统 - Streamlit Web 应用
上传文档，AI 自动生成选择题/判断题/填空题，在线作答并查看解析。
"""
import os
import queue
import threading
import time
from typing import Any

from dotenv import load_dotenv
import streamlit as st

load_dotenv()

_gen_queue: queue.Queue = queue.Queue()

from utils.file_parser import parse_file
from utils.question_gen import Question, generate_questions
from ui.sidebar import render_sidebar
from ui.quiz import grade_choice, grade_fill_blank, render_questions, render_results


# ── 文件解析缓存 ─────────────────────────────────────────
@st.cache_data(show_spinner="正在解析文件...")
def _cached_parse_file(file_bytes: bytes, filename: str) -> str:
    return parse_file(file_bytes, filename)


# ── 后台出题 ─────────────────────────────────────────────
def _launch_generation(**kwargs: Any) -> None:
    def _progress(msg: str) -> None:
        _gen_queue.put(("progress", msg))

    def _worker():
        try:
            questions = generate_questions(progress_callback=_progress, **kwargs)
            _gen_queue.put(("result", questions))
        except Exception as e:
            _gen_queue.put(("error", str(e)))
    threading.Thread(target=_worker, daemon=True).start()


# ── 页面配置 ─────────────────────────────────────────────
st.set_page_config(page_title="智能出题系统", page_icon="📝", layout="wide",
                   initial_sidebar_state="expanded")

CSS_PATH = os.path.join(os.path.dirname(__file__), "style.css")
if os.path.exists(CSS_PATH):
    with open(CSS_PATH, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Session State ────────────────────────────────────────
defaults: dict[str, Any] = {
    "extracted_text": "",
    "questions": [],
    "submitted": False,
    "generating": False,
    "gen_error": None,
    "quiz_start_time": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 暗黑主题 ─────────────────────────────────────────────
st.markdown(
    '<script>document.documentElement.setAttribute("data-theme","dark")</script>',
    unsafe_allow_html=True,
)

# ── HUD 鼠标追踪 & 卡片视差 ──────────────────────────────
st.markdown("""<script>
(function(){
  "use strict";
  var glow=document.getElementById("cursor-glow");
  if(!glow){glow=document.createElement("div");glow.id="cursor-glow";document.body.appendChild(glow)}
  var mx=-1000,my=-1000,cx=-1000,cy=-1000,vis=false;
  var inert=0;
  document.addEventListener("mousemove",function(e){
    mx=e.clientX;my=e.clientY;
    if(!vis){vis=true;glow.classList.remove("glow-hidden");cx=mx;cy=my;glow.style.left=mx+"px";glow.style.top=my+"px"}
    inert=0;
  });
  document.addEventListener("mouseleave",function(){vis=false;glow.classList.add("glow-hidden")});
  !function anim(){if(vis){cx+=(mx-cx)*0.08;cy+=(my-cy)*0.08;glow.style.left=cx+"px";glow.style.top=cy+"px"}requestAnimationFrame(anim)}();

  function initCards(){
    var cards=document.querySelectorAll(".question-card");
    for(var i=0;i<cards.length;i++){
      (function(card){
        if(card.dataset.hudReady)return;
        card.dataset.hudReady="1";
        var g=card.querySelector(".card-glow");
        if(!g){g=document.createElement("div");g.className="card-glow";card.appendChild(g)}
        card.addEventListener("mousemove",function(e){
          var r=card.getBoundingClientRect();
          var x=e.clientX-r.left,y=e.clientY-r.top;
          var cx_=r.width/2,cy_=r.height/2;
          var rx=((y-cy_)/cy_)*-5,ry=((x-cx_)/cx_)*5;
          card.style.transform="perspective(600px) rotateX("+rx+"deg) rotateY("+ry+"deg) scale3d(1.01,1.01,1.01)";
          g.style.left=x+"px";g.style.top=y+"px";g.style.opacity="1";
        });
        card.addEventListener("mouseleave",function(){
          card.style.transform="perspective(600px) rotateX(0deg) rotateY(0deg) scale3d(1,1,1)";
          g.style.opacity="0";
        });
      })(cards[i]);
    }
  }
  initCards();
  new MutationObserver(function(){initCards()}).observe(document.body,{childList:true,subtree:true});
})();
\x3c/script>""", unsafe_allow_html=True)

# ── 侧边栏 ──────────────────────────────────────────────
with st.sidebar:
    cfg = render_sidebar()

api_key = cfg["api_key"]
base_url = cfg["base_url"]
model = cfg["model"]
num_questions = cfg["num_questions"]
difficulty = cfg["difficulty"]
subject = cfg["subject"]
language = cfg["language"]
question_type_mode = cfg["question_type_mode"]

# ── 主界面 ──────────────────────────────────────────────
st.title("📝 智能出题系统")
st.markdown(
    "上传文档（PDF / Word / 纯文本 / Markdown），AI 自动生成题目（选择题/判断题/填空题），帮你快速检验学习成果。"
)

# ── 上传区域 ────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "选择文件", type=["pdf", "docx", "doc", "txt", "md"],
    help="支持 PDF、Word (.docx)、纯文本 (.txt)、Markdown (.md)",
)

col1, col2 = st.columns([3, 1])
with col1:
    if st.session_state.extracted_text:
        with st.expander("📄 已提取的文本预览", expanded=False):
            st.text_area(
                "文本内容", st.session_state.extracted_text[:2000],
                height=200, disabled=True, label_visibility="collapsed",
            )
            if len(st.session_state.extracted_text) > 2000:
                st.caption(f"... 共 {len(st.session_state.extracted_text)} 字符，仅显示前 2000 字符")
with col2:
    st.metric("文本长度", f"{len(st.session_state.extracted_text)} 字符")

# ── 文件解析 ────────────────────────────────────────────
if uploaded_file is not None:
    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        if not file_bytes:
            st.error("❌ 文件内容为空，无法解析")
            st.session_state.extracted_text = ""
        else:
            extracted = _cached_parse_file(file_bytes, uploaded_file.name)
            is_new = extracted != st.session_state.extracted_text
            if is_new:
                st.session_state.extracted_text = extracted
                st.session_state.questions = []
                st.session_state.submitted = False
                st.session_state.quiz_start_time = None
            if not extracted:
                st.warning(f"⚠️ 文件「{uploaded_file.name}」解析完成，但未提取到文字。")
            elif is_new:
                st.success(f"✅ 文件「{uploaded_file.name}」解析成功！共提取 {len(extracted)} 字符")
    except Exception as e:
        st.error(f"❌ 文件解析失败: {e}")
        st.session_state.extracted_text = ""

# ── 生成按钮 ────────────────────────────────────────────
col_left, _, col_right = st.columns([1, 2, 1])

def _do_generate() -> None:
    st.session_state.generating = True
    st.session_state.submitted = False
    st.session_state.questions = []
    st.session_state.gen_error = None
    _launch_generation(
        text=st.session_state.extracted_text,
        num_questions=num_questions,
        difficulty=difficulty,
        subject=subject,
        api_key=api_key or None,
        base_url=base_url or None,
        model=model,
        language="zh" if language == "中文" else "en",
        question_types="mixed" if "混合" in question_type_mode else "choice",
    )

with col_left:
    gen_disabled = (
        not api_key
        or not st.session_state.extracted_text
        or st.session_state.generating
    )
    if st.button("🚀 开始出题", type="primary", use_container_width=True,
                  disabled=gen_disabled):
        st.session_state.quiz_start_time = None
        _do_generate()
        st.rerun()

with col_right:
    if st.session_state.questions:
        if st.button("🔄 重新出题", use_container_width=True):
            _do_generate()
            st.rerun()

# ── 生成状态（主线程轮询） ──────────────────────────────
if st.session_state.generating and st.session_state.extracted_text:
    status_placeholder = st.status("🤖 AI 正在出题中...", expanded=True)

    try:
        msg_type, payload = _gen_queue.get_nowait()
        if msg_type == "progress":
            status_placeholder.update(label=f"🤖 {payload}", expanded=True)
        elif msg_type == "result":
            questions = payload
            status_placeholder.update(label=f"✅ 出题完成！共生成 {len(questions)} 道题",
                                      state="complete", expanded=False)
            st.session_state.questions = questions
            st.session_state.generating = False
            st.session_state.quiz_start_time = None
            st.rerun()
        elif msg_type == "error":
            err = payload
            st.session_state.gen_error = err
            status_placeholder.update(label=f"❌ 出题失败: {err}", state="error")
    except queue.Empty:
        pass

    if st.session_state.gen_error is not None:
        col_r1, col_r2 = st.columns([1, 3])
        with col_r1:
            if st.button("🔄 重试", key="retry_gen", use_container_width=True):
                st.session_state.gen_error = None
                _do_generate()
                st.rerun()
        with col_r2:
            st.caption("建议检查 API Key 是否正确、网络是否通畅")
    else:
        if st.button("取消", key="cancel_gen"):
            st.session_state.generating = False
            st.rerun()

    # 自动轮询（用 st.rerun 保持 session 不断，避免整页重载）
    if st.session_state.generating and st.session_state.gen_error is None:
        time.sleep(2)
        st.rerun()

# ── 题目展示和作答 ──────────────────────────────────────
questions = st.session_state.questions
if questions:
    # 初始化用户答案
    user_answers: dict[int, str] = {}
    if "persisted_answers" not in st.session_state:
        st.session_state.persisted_answers = {}

    # 计时开始（首次渲染题目时）
    if st.session_state.quiz_start_time is None:
        st.session_state.quiz_start_time = time.time()

    grades: dict[int, tuple[bool, str, str]] = {}
    if st.session_state.submitted:
        for i, q in enumerate(questions[:]):
            ua = st.session_state.persisted_answers.get(i, "")
            if q.question_type in ("choice", "true_false"):
                grades[i] = grade_choice(q, ua)
            else:
                grades[i] = grade_fill_blank(q, ua)

    render_questions(
        questions,
        submitted=st.session_state.submitted,
        grades=grades,
        user_answers=st.session_state.persisted_answers if not st.session_state.submitted else user_answers,
    )

    # 提交按钮
    if not st.session_state.submitted:
        st.markdown("---")
        if st.button("📝 提交批改", type="primary", use_container_width=True):
            # 搜集所有答案
            for i in range(len(questions)):
                key = f"ans_{i}"
                if key in st.session_state:
                    st.session_state.persisted_answers[i] = st.session_state[key]
            st.session_state.submitted = True
            st.rerun()
    else:
        render_results(questions, st.session_state.persisted_answers, grades)

        # 重新作答 / 继续编辑
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 重新作答", use_container_width=True):
                st.session_state.submitted = False
                st.session_state.persisted_answers = {}
                st.session_state.quiz_start_time = time.time()
                st.rerun()
        with c2:
            if st.button("📝 继续编辑答案", use_container_width=True):
                for i in range(len(questions)):
                    key = f"ans_{i}"
                    if key in st.session_state:
                        st.session_state.persisted_answers[i] = st.session_state[key]
                st.session_state.submitted = False
                st.rerun()
