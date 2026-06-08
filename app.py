"""
智能出题系统 - Streamlit Web 应用
支持上传 PDF / Word / 纯文本 / Markdown 文件，自动生成选择题
"""

import os
import threading

from dotenv import load_dotenv
import streamlit as st

load_dotenv()  # 加载 .env 文件中的环境变量

from utils.file_parser import parse_file
from utils.question_gen import Question, generate_questions


# ── 文件解析缓存（避免 rerun 重复解析）──────────────────────
@st.cache_data(show_spinner="正在解析文件...")
def _cached_parse_file(file_bytes: bytes, filename: str) -> str:
    """解析文件并缓存结果，相同文件内容不会重复解析。"""
    return parse_file(file_bytes, filename)


# ── 后台出题 ──────────────────────────────────────────────
def _launch_generation(**kwargs):
    """在后台线程中调用 AI 出题，不阻塞 Streamlit UI。"""
    def _worker():
        try:
            questions = generate_questions(**kwargs)
            if not st.session_state.cancel_generation:
                st.session_state.gen_result = questions
        except Exception as e:
            st.session_state.gen_error = str(e)

    threading.Thread(target=_worker, daemon=True).start()


# ── 批改函数 ──────────────────────────────────────────────
def _grade_choice(q: Question, i: int) -> tuple[bool, str, str]:
    """批改选择题/判断题，返回 (是否正确, 用户答案显示, 正确答案显示)"""
    options = q.options
    selected = st.session_state.get(f"q_{i}")
    if selected is None:
        correct_text = (
            options[q.correct_index] if q.correct_index < len(options) else "未知"
        )
        return False, "未作答", correct_text

    try:
        selected_idx = options.index(selected)
    except ValueError:
        return False, selected, (options[q.correct_index] if q.correct_index < len(options) else "未知")

    is_correct = selected_idx == q.correct_index
    correct_text = options[q.correct_index] if q.correct_index < len(options) else "未知"
    return is_correct, selected, correct_text


def _grade_fill_blank(q: Question, i: int) -> tuple[bool, str, str]:
    """批改填空题，返回 (是否正确, 用户答案显示, 正确答案显示)"""
    user_answer = st.session_state.get(f"q_{i}_text", "").strip()
    if not user_answer:
        return False, "未作答", q.correct_answer

    # 标准化比较：去空格、转小写
    normalized_user = user_answer.replace(" ", "").lower()
    normalized_correct = q.correct_answer.replace(" ", "").lower()

    # 1. 精确匹配
    if normalized_user == normalized_correct:
        return True, user_answer, q.correct_answer

    # 2. 检查可接受的其他答案
    for alt in q.acceptable_answers:
        if normalized_user == alt.replace(" ", "").lower():
            return True, user_answer, q.correct_answer

    # 3. 模糊匹配：包含关系（如用户写"光合作用"，答案是"植物的光合作用"）
    if normalized_correct and (
        normalized_correct in normalized_user or normalized_user in normalized_correct
    ):
        return True, user_answer, q.correct_answer

    return False, user_answer, q.correct_answer


# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(
    page_title="智能出题系统",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 样式 ──────────────────────────────────────────────────
CSS_PATH = os.path.join(os.path.dirname(__file__), "style.css")
if os.path.exists(CSS_PATH):
    with open(CSS_PATH, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Session State 初始化 ─────────────────────────────────
if "extracted_text" not in st.session_state:
    st.session_state.extracted_text = ""
if "questions" not in st.session_state:
    st.session_state.questions: list[Question] = []
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "generating" not in st.session_state:
    st.session_state.generating = False
if "gen_result" not in st.session_state:
    st.session_state.gen_result = None  # list[Question] | None
if "gen_error" not in st.session_state:
    st.session_state.gen_error = None  # str | None
if "cancel_generation" not in st.session_state:
    st.session_state.cancel_generation = False
# ── 固定应用暗黑主题 ─────────────────────────────────────
st.markdown('<script>document.documentElement.setAttribute("data-theme","dark")</script>', unsafe_allow_html=True)


# ── 侧边栏：配置 ──────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 配置")

    # 服务商选择
    provider = st.selectbox(
        "AI 服务商",
        options=["DeepSeek（推荐，注册送额度）", "OpenAI", "自定义"],
        index=0,
        help="DeepSeek 注册即送额度，价格便宜，兼容 OpenAI 格式。",
    )

    # 根据服务商自动填充默认值
    provider_defaults = {
        "DeepSeek（推荐，注册送额度）": {
            "key_label": "DeepSeek API Key",
            "key_placeholder": "sk-...",
            "key_help": "在 platform.deepseek.com 获取",
            "base_url": "https://api.deepseek.com",
            "base_url_disabled": False,
            "model_options": ["deepseek-chat"],
            "model_default": "deepseek-chat",
            "model_help": "DeepSeek-V3 模型，性价比极高",
        },
        "OpenAI": {
            "key_label": "OpenAI API Key",
            "key_placeholder": "sk-...",
            "key_help": "在 platform.openai.com 获取",
            "base_url": "",
            "base_url_disabled": False,
            "model_options": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            "model_default": "gpt-4o-mini",
            "model_help": "gpt-4o-mini 性价比最高，gpt-4o 质量更好但更贵",
        },
        "自定义": {
            "key_label": "API Key",
            "key_placeholder": "sk-...",
            "key_help": "输入你的 API Key",
            "base_url": "",
            "base_url_disabled": False,
            "model_options": ["gpt-4o-mini", "deepseek-chat", "qwen-plus", "glm-4-plus", "其他"],
            "model_default": "deepseek-chat",
            "model_help": "根据你使用的服务商选择对应模型",
        },
    }

    defaults = provider_defaults[provider]

    # 根据服务商选择对应的环境变量名
    if provider == "DeepSeek（推荐，注册送额度）":
        default_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        default_base_url = os.getenv("DEEPSEEK_BASE_URL", defaults["base_url"])
    elif provider == "OpenAI":
        default_api_key = os.getenv("OPENAI_API_KEY", "")
        default_base_url = os.getenv("OPENAI_BASE_URL", defaults["base_url"])
    else:  # 自定义
        default_api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        default_base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or defaults["base_url"]

    # API Key 输入
    api_key = st.text_input(
        defaults["key_label"],
        type="password",
        value=default_api_key,
        help=defaults["key_help"],
        placeholder=defaults["key_placeholder"],
    )

    # API 地址
    base_url = st.text_input(
        "API 地址",
        value=default_base_url,
        placeholder="https://api.deepseek.com",
        help="AI 服务商的 API 地址",
        disabled=defaults["base_url_disabled"],
    )

    # 模型选择
    model = st.selectbox(
        "AI 模型",
        options=defaults["model_options"],
        index=0,
        help=defaults["model_help"],
    )
    # 如果选择了「自定义」且选了「其他」，允许手动输入模型
    if provider == "自定义" and model == "其他":
        model = st.text_input("请输入模型名称", value="deepseek-chat")

    # 题目数量
    num_questions = st.slider("出题数量", min_value=1, max_value=50, value=5)

    # 难度级别
    difficulty = st.slider(
        "难度级别",
        min_value=1, max_value=5, value=3,
        format="%d 级",
        help="1=非常简单（原文直给）  3=适中  5=困难（深层推理）",
    )

    # 语言
    language = st.radio("题目语言", options=["中文", "English"], index=0)

    # 题型模式
    question_type_mode = st.radio(
        "题型模式",
        options=["仅选择题", "混合题（选择+判断+填空）"],
        index=0,
        help="混合题将包含选择题、判断题和填空题三种题型",
    )

    st.divider()
    st.caption("💡 使用提示")
    st.caption(
        """
1. 选择服务商并填入 API Key
2. 上传文件 (PDF/Word/文本)
3. 点击「开始出题」
4. 作答并查看解析
        """
    )
    st.caption("---")
    st.caption("🔑 DeepSeek 注册：https://platform.deepseek.com")
    st.caption("📌 API Key 仅在本次会话内存中使用，不会存储或上传到其他地方。")


# ── 主界面 ────────────────────────────────────────────────
st.title("📝 智能出题系统")
st.markdown(
    "上传文档（PDF / Word / 纯文本 / Markdown），AI 自动生成题目（选择题/判断题/填空题），帮你快速检验学习成果。"
)

# ── 上传区域 ──────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "选择文件",
    type=["pdf", "docx", "doc", "txt", "md"],
    help="支持 PDF、Word (.docx)、纯文本 (.txt)、Markdown (.md)",
)

col1, col2 = st.columns([3, 1])

with col1:
    # 如果已经有提取的文本，显示预览
    if st.session_state.extracted_text:
        with st.expander("📄 已提取的文本预览", expanded=False):
            st.text_area(
                "文本内容",
                st.session_state.extracted_text[:2000],
                height=200,
                disabled=True,
                label_visibility="collapsed",
            )
            if len(st.session_state.extracted_text) > 2000:
                st.caption(f"... 共 {len(st.session_state.extracted_text)} 字符，仅显示前 2000 字符")

with col2:
    st.metric("文本长度", f"{len(st.session_state.extracted_text)} 字符")

# ── 处理上传文件 ──────────────────────────────────────────
if uploaded_file is not None:
    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        if not file_bytes:
            st.error("❌ 文件内容为空，无法解析")
            st.session_state.extracted_text = ""
        else:
            extracted = _cached_parse_file(file_bytes, uploaded_file.name)

            # 只在文本真正改变时才清空题目（避免 rerun 误清已生成的题目）
            is_new_file = extracted != st.session_state.extracted_text
            if is_new_file:
                st.session_state.extracted_text = extracted
                st.session_state.questions = []
                st.session_state.submitted = False

            if not extracted:
                st.warning(
                    f"⚠️ 文件「{uploaded_file.name}」解析完成，但未提取到文字。"
                    "可能原因：\n"
                    "- PDF 是扫描件/图片，没有文字层\n"
                    "- Word 文档中只有图片没有文字\n"
                    "- 文件是空的"
                )
            elif is_new_file:
                st.success(f"✅ 文件「{uploaded_file.name}」解析成功！共提取 {len(extracted)} 字符")
    except Exception as e:
        st.error(f"❌ 文件解析失败: {e}")
        st.session_state.extracted_text = ""

# ── 生成按钮 ──────────────────────────────────────────────
col_left, _, col_right = st.columns([1, 2, 1])

with col_left:
    generate_disabled = (
        not api_key
        or not st.session_state.extracted_text
        or st.session_state.generating
    )
    if st.button(
        "🚀 开始出题",
        type="primary",
        use_container_width=True,
        disabled=generate_disabled,
    ):
        if not api_key:
            st.warning("请在左侧边栏输入 API Key（已默认为 DeepSeek，注册即送额度）")
        elif not st.session_state.extracted_text:
            st.warning("请先上传文件")
        else:
            st.session_state.generating = True
            st.session_state.submitted = False
            st.session_state.gen_result = None
            st.session_state.gen_error = None
            st.session_state.cancel_generation = False
            # 在后台线程中出题，不阻塞 UI
            _launch_generation(
                text=st.session_state.extracted_text,
                num_questions=num_questions,
                difficulty=difficulty,
                api_key=api_key or None,
                base_url=base_url or None,
                model=model,
                language="zh" if language == "中文" else "en",
                question_types="mixed" if "混合" in question_type_mode else "choice",
            )
            st.rerun()

with col_right:
    if st.session_state.questions:
        if st.button("🔄 重新出题", use_container_width=True):
            st.session_state.generating = True
            st.session_state.submitted = False
            st.session_state.questions = []
            st.session_state.gen_result = None
            st.session_state.gen_error = None
            st.session_state.cancel_generation = False
            _launch_generation(
                text=st.session_state.extracted_text,
                num_questions=num_questions,
                difficulty=difficulty,
                api_key=api_key or None,
                base_url=base_url or None,
                model=model,
                language="zh" if language == "中文" else "en",
                question_types="mixed" if "混合" in question_type_mode else "choice",
            )
            st.rerun()


# ── 生成状态（后台线程执行，不阻塞 UI）──────────────────────
if st.session_state.generating and st.session_state.extracted_text:
    status_placeholder = st.status("🤖 AI 正在出题中...", expanded=True)

    # 检查后台线程是否已完成
    if st.session_state.gen_result is not None:
        questions = st.session_state.gen_result
        status_placeholder.update(
            label=f"✅ 出题完成！共生成 {len(questions)} 道题",
            state="complete", expanded=False,
        )
        st.session_state.questions = questions
        st.session_state.generating = False
        st.session_state.gen_result = None
        st.rerun()

    elif st.session_state.gen_error is not None:
        error_msg = st.session_state.gen_error
        status_placeholder.update(label="❌ 出题失败", state="error", expanded=True)
        st.session_state.generating = False
        st.error(f"❌ 出题失败: {error_msg}")
        if any(kw in error_msg.lower() for kw in ["api_key", "401", "unauthorized", "api密钥", "认证"]):
            st.info("💡 请检查 API Key 是否正确，或更换 API 地址")
        st.session_state.gen_error = None
        st.rerun()

    else:
        # 仍在生成中 — 显示取消按钮
        status_placeholder.write("📄 AI 正在分析文本并生成题目...")
        if st.button("⏹ 取消出题", use_container_width=True):
            st.session_state.cancel_generation = True
            st.session_state.generating = False
            st.session_state.gen_result = None
            st.rerun()
        # 自动轮询线程状态
        st.rerun()


# ── 显示题目 ──────────────────────────────────────────────
if st.session_state.questions:
    questions = st.session_state.questions
    st.divider()
    # 统计各题型数量
    type_counts = {}
    for q in questions:
        t = q.question_type
        type_counts[t] = type_counts.get(t, 0) + 1
    type_labels = {"choice": "选择题", "true_false": "判断题", "fill_blank": "填空题"}
    type_summary = " ｜ ".join(
        f"{type_labels.get(t, t)} × {c}" for t, c in type_counts.items()
    )
    st.subheader(f"📋 共生成 {len(questions)} 道题（{type_summary}）")

    # 答题表单
    with st.form("quiz_form"):
        for i, q in enumerate(questions):
            st.markdown(f'<div class="question-card">', unsafe_allow_html=True)

            # 题型标签
            type_tag = type_labels.get(q.question_type, q.question_type)

            st.markdown(
                f'<div class="question-text">第 {i + 1} 题【{type_tag}】：{q.question}</div>',
                unsafe_allow_html=True,
            )

            if q.question_type in ("choice", "true_false"):
                # ── 选择题 / 判断题：单选按钮 ──
                options = q.options
                # 判断题如果 AI 没给选项，自动补上
                if q.question_type == "true_false" and (not options or len(options) < 2):
                    options = ["A. 正确", "B. 错误"]
                # 选择题保留原始选项（不再补齐）

                selected = st.radio(
                    "选择答案",
                    options=options,
                    index=None,
                    key=f"q_{i}",
                    label_visibility="collapsed",
                    horizontal=True,
                )

                if selected:
                    selected_idx = options.index(selected)

            elif q.question_type == "fill_blank":
                # ── 填空题：文本输入 ──
                st.text_input(
                    "请输入答案",
                    key=f"q_{i}_text",
                    placeholder="在此输入你的答案...",
                    label_visibility="collapsed",
                )

            st.markdown("</div>", unsafe_allow_html=True)

        # 提交按钮
        submitted = st.form_submit_button("📤 提交答案", type="primary", use_container_width=True)

    if submitted:
        st.session_state.submitted = True
        st.rerun()

    # ── 显示结果 ──────────────────────────────────────────
    if st.session_state.submitted:
        st.divider()
        st.subheader("📊 答题结果")

        type_labels = {"choice": "选择题", "true_false": "判断题", "fill_blank": "填空题"}

        correct_count = 0
        for i, q in enumerate(questions):
            type_tag = type_labels.get(q.question_type, q.question_type)

            if q.question_type in ("choice", "true_false"):
                is_correct, user_display, correct_display = _grade_choice(q, i)
            elif q.question_type == "fill_blank":
                is_correct, user_display, correct_display = _grade_fill_blank(q, i)
            else:
                is_correct, user_display, correct_display = False, "未知", "未知"

            if is_correct:
                correct_count += 1
                st.markdown(
                    f'✅ **第 {i + 1} 题【{type_tag}】**  {q.question}  '
                    f'<span class="correct-badge">✓ 正确</span>',
                    unsafe_allow_html=True,
                )
            elif user_display == "未作答":
                st.markdown(
                    f'⚠️ **第 {i + 1} 题【{type_tag}】** {q.question} — 未作答',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'❌ **第 {i + 1} 题【{type_tag}】**  {q.question}  '
                    f'<span class="wrong-badge">✗ 错误</span>',
                    unsafe_allow_html=True,
                )

            if user_display != "未作答":
                st.markdown(f"- 你的答案：{user_display}")
            st.markdown(f"- 正确答案：{correct_display}")

            st.markdown(
                f'<div class="explanation-box">💡 {q.explanation}</div>',
                unsafe_allow_html=True,
            )

            if i < len(questions) - 1:
                st.divider()

        # 总分
        total = len(questions)
        percentage = int(correct_count / total * 100) if total > 0 else 0
        st.markdown(
            f"""
        <div style="
            text-align: center;
            padding: 2rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px;
            color: white;
            margin-top: 1rem;
        ">
            <h2>🏆 {correct_count} / {total}  正确率 {percentage}%</h2>
        </div>
        """,
            unsafe_allow_html=True,
        )

# ── 空状态 ────────────────────────────────────────────────
if not st.session_state.questions and not st.session_state.extracted_text:
    st.info("👆 上传文件并点击「开始出题」来生成题目")

elif not st.session_state.questions and st.session_state.extracted_text:
    st.info("👆 点击「开始出题」按钮生成题目")
