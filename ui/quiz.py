"""
作答与批改模块 — 题目展示、作答输入、批改、结果统计、导出、计时
"""
import base64
import csv
import io
import time
import streamlit as st

from utils.question_gen import Question


# ── 批改函数 ──────────────────────────────────────────────

def grade_choice(q: Question, user_answer: str) -> tuple[bool, str, str]:
    """批改选择题/判断题。返回 (是否正确, 用户答案, 正确答案)。"""
    if not user_answer:
        return False, "未作答", _option_text(q)
    correct_text = _option_text(q)
    return user_answer.upper().startswith(chr(65 + q.correct_index)), user_answer, correct_text


def grade_fill_blank(q: Question, user_answer: str) -> tuple[bool, str, str]:
    """批改填空题。返回 (是否正确, 用户答案, 正确答案)。"""
    if not user_answer.strip():
        return False, "未作答", q.correct_answer
    normalized_user = user_answer.strip().lower()
    normalized_correct = q.correct_answer.strip().lower()
    if normalized_correct and (
        normalized_correct in normalized_user or normalized_user in normalized_correct
    ):
        return True, user_answer, q.correct_answer
    return False, user_answer, q.correct_answer


def _option_text(q: Question) -> str:
    """获取选择题正确答案的文本。"""
    if q.options and 0 <= q.correct_index < len(q.options):
        return q.options[q.correct_index]
    return str(q.correct_index)


# ── 导出 ─────────────────────────────────────────────────

def _export_csv(
    questions: list[Question],
    user_answers: dict[int, str],
    grades: dict[int, tuple[bool, str, str]],
) -> bytes:
    """将批改结果导出为 CSV 字节流"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["#", "题型", "题目", "你的答案", "正确答案", "结果", "解析"])
    for i, q in enumerate(questions[:]):
        ok, ua, ca = grades.get(i, (False, user_answers.get(i, ""), ""))
        writer.writerow([
            i + 1,
            q.question_type,
            q.question,
            ua,
            ca,
            "✓ 正确" if ok else "✗ 错误",
            q.explanation,
        ])
    return buf.getvalue().encode("utf-8-sig")


def _render_export_button(questions: list[Question],
                          user_answers: dict[int, str],
                          grades: dict[int, tuple[bool, str, str]]):
    """渲染导出按钮（CSV 下载）。"""
    csv_data = _export_csv(questions, user_answers, grades)
    b64 = base64.b64encode(csv_data).decode()
    href = f'<a href="data:text/csv;base64,{b64}" download="quiz_results.csv" class="export-link">📥 导出成绩 CSV</a>'
    st.markdown(href, unsafe_allow_html=True)


# ── 计时 ─────────────────────────────────────────────────

def _render_timer(start_ts: float):
    """渲染计时器 UI。"""
    elapsed = max(0, time.time() - start_ts)
    mins, secs = divmod(int(elapsed), 60)
    st.sidebar.metric("⏱ 作答时间", f"{mins:02d}:{secs:02d}")


# ── 题目渲染 ─────────────────────────────────────────────

def render_questions(
    questions: list[Question],
    submitted: bool,
    grades: dict[int, tuple[bool, str, str]],
    user_answers: dict[int, str],
):
    """渲染题目列表和作答区域，含编辑/删除功能。

    Args:
        questions: 题目列表
        submitted: 是否已提交批改
        grades: 批改结果 {索引: (是否正确, 用户答案, 正确答案)}
        user_answers: 用户答案 {索引: 答案文本}
    """
    # 计时器
    if st.session_state.get("quiz_start_time"):
        _render_timer(st.session_state.quiz_start_time)

    st.markdown("---")
    st.subheader("📋 作答区")

    for i, q in enumerate(questions[:]):
        with st.container():
            st.markdown(f'<div class="question-card">', unsafe_allow_html=True)

            # 题目头部
            col_title, col_del = st.columns([10, 1])
            with col_title:
                type_label = {"choice": "选择题", "true_false": "判断题", "fill_blank": "填空题"}
                st.markdown(
                    f'<div class="question-text">{i+1}. [{type_label.get(q.question_type, "未知")}] {q.question}</div>',
                    unsafe_allow_html=True,
                )

            # 删除按钮
            with col_del:
                if st.button("🗑", key=f"del_{i}", help="删除此题"):
                    questions.pop(i)
                    st.rerun()

            # 已提交时显示批改结果
            if submitted and i in grades:
                ok, ua, ca = grades[i]
                badge_class = "correct-badge" if ok else "wrong-badge"
                badge_text = "✓ 正确" if ok else "✗ 错误"
                st.markdown(f'<span class="{badge_class}">{badge_text}</span>', unsafe_allow_html=True)

                if q.explanation:
                    st.markdown(
                        f'<div class="explanation-box">{q.explanation}</div>',
                        unsafe_allow_html=True,
                    )
                if not ok and ca:
                    st.caption(f"正确答案: {ca}")
                    # 提示编辑
                    if st.button("✏️ 编辑答案", key=f"edit_{i}"):
                        st.session_state[f"edit_answer_{i}"] = True
                        st.rerun()

            # 未提交或正在编辑 → 显示作答输入
            if not submitted or st.session_state.get(f"edit_answer_{i}"):
                if q.question_type in ("choice", "true_false"):
                    options_display = q.options or []
                    if not options_display and q.question_type == "true_false":
                        options_display = ["A. 正确", "B. 错误"]
                    prev_val = user_answers.get(i, "")
                    prev_index = None
                    for oi, opt in enumerate(options_display):
                        if opt.startswith(prev_val):
                            prev_index = oi
                            break
                    user_answers[i] = st.radio(
                        "你的答案",
                        options=options_display,
                        index=prev_index,
                        key=f"ans_{i}",
                        label_visibility="collapsed",
                    )
                else:
                    user_answers[i] = st.text_input(
                        "你的答案",
                        value=user_answers.get(i, ""),
                        key=f"ans_{i}",
                        label_visibility="collapsed",
                        placeholder="请输入填空答案...",
                    )

            st.markdown('</div>', unsafe_allow_html=True)


def render_results(questions: list[Question],
                   user_answers: dict[int, str],
                   grades: dict[int, tuple[bool, str, str]]):
    """渲染批改结果统计和导出按钮。

    Args:
        questions: 题目列表
        user_answers: 用户答案 {索引: 答案文本}
        grades: 批改结果 {索引: (是否正确, 用户答案, 正确答案)}
    """
    st.markdown("---")
    st.subheader("📊 成绩单")

    total = len(questions)
    if total == 0:
        st.info("没有题目可供批改。")
        return

    correct_count = sum(1 for v in grades.values() if v[0])
    score_pct = round(correct_count / total * 100, 1)

    col1, col2, col3 = st.columns(3)
    col1.metric("总题数", total)
    col2.metric("答对", correct_count)
    col3.metric("正确率", f"{score_pct}%")

    # 计时
    if st.session_state.get("quiz_start_time"):
        elapsed = max(0, time.time() - st.session_state.quiz_start_time)
        mins, secs = divmod(int(elapsed), 60)
        st.caption(f"⏱ 用时: {mins:02d}:{secs:02d}")

    # 导出按钮
    _render_export_button(questions, user_answers, grades)

    # 评价
    if score_pct >= 90:
        st.success("🌟 太棒了！成绩非常优秀！")
    elif score_pct >= 70:
        st.success("👍 不错，继续加油！")
    elif score_pct >= 50:
        st.warning("📖 还行，再看看错题的解析吧")
    else:
        st.error("📚 需要多复习一下哦")
