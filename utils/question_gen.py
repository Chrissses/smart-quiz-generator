"""
AI 出题模块 - 调用 LLM 根据文本内容自动生成选择题
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from math import ceil
from typing import Callable, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class Question:
    """一道题的数据结构，支持多种题型"""
    question: str = ""
    question_type: str = "choice"  # "choice", "true_false", "fill_blank"
    options: list[str] = field(default_factory=list)  # 选择题/判断题的选项
    correct_index: int = 0  # 选择题/判断题的正确答案索引 (0-based)
    correct_answer: str = ""   # 填空题的标准答案
    acceptable_answers: list[str] = field(default_factory=list)  # 填空题可接受的其他答案
    explanation: str = ""   # 答案解析

    def to_dict(self) -> dict:
        return asdict(self)


# 系统提示词 - 控制 AI 的出题行为
SYSTEM_PROMPT = """你是一位专业的考试出题老师。你需要根据用户提供的文本内容，生成高质量的考试题目。

## 出题原则
1. **紧扣原文**：所有题目必须基于给定文本中的知识点，不要编造文本中没有的内容
2. **难度适中**：题目要有一定思考价值，不能太简单（直接抄原文）也不能太难（推理过度）
3. **选项合理**：选择题的 4 个选项中，干扰项要有迷惑性，不能明显错误
4. **答案明确**：正确答案必须唯一且确定
5. **解析精炼**：用 1-2 句话解释为什么选这个答案，引用原文依据

## 支持的题型
你可以生成以下 3 种题型，混合搭配效果更好：

### 1. 选择题 (choice)
- 4 个选项，每个选项以 "A. ", "B. ", "C. ", "D. " 开头
- correct_index 为 0-based，即 A=0, B=1, C=2, D=3

### 2. 判断题 (true_false)
- 正好 2 个选项：["A. 正确", "B. 错误"]
- correct_index: 正确为 0，错误为 1

### 3. 填空题 (fill_blank)
- 题目中用（___）或 ____ 表示填空位置
- 提供 correct_answer（标准答案）
- acceptable_answers 数组列出可接受的同义答案（如别名、常见变体）
- 不需要 options 和 correct_index 字段

## 输出格式
你必须严格按照以下 JSON 格式输出，不要包含任何额外内容：

```json
[
  {
    "question_type": "choice",
    "question": "题目标题",
    "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
    "correct_index": 0,
    "explanation": "答案解析"
  },
  {
    "question_type": "true_false",
    "question": "判断正误：...",
    "options": ["A. 正确", "B. 错误"],
    "correct_index": 0,
    "explanation": "答案解析"
  },
  {
    "question_type": "fill_blank",
    "question": "...（___）...",
    "correct_answer": "标准答案",
    "acceptable_answers": ["同义答案1", "常见变体2"],
    "explanation": "答案解析"
  }
]
```

注意：
- 必须包含 "question_type" 字段，取值为 "choice" / "true_false" / "fill_blank"
- 确保输出的 JSON 是合法的、可解析的"""


# 难度级别对应的提示词
DIFFICULTY_PROMPTS = {
    1: "【难度：非常简单】题目应直接基于原文字面内容，答案在原文中几乎原样可找到。选项区分度明显，干扰项与原文明显不同。",
    2: "【难度：简单】题目基于原文明显知识点，答案能在原文中较快定位。选项有一定迷惑性，但正确答案仍较明显。",
    3: "【难度：适中】题目需要理解原文段落才能作答。选项有较强迷惑性，需要排除干扰项。涉及适度的归纳和推断。",
    4: "【难度：较难】题目需要综合理解多个段落或全文才能作答。选项高度相似，需要仔细辨析。涉及跨段落的推理和总结。",
    5: "【难度：困难】题目需要深层分析和综合推理，答案不能直接在原文中找到。选项极具迷惑性，考察对概念的真正理解而非记忆。涉及批判性思维和知识迁移。",
}


def _chunk_text(text: str, max_chars: int = 8000, max_chunks: int = 5) -> list[str]:
    """将长文本按段落边界切分为多个块，每块不超过 max_chars 字符。"""
    paragraphs = [p for p in text.split('\n') if p.strip()]
    if not paragraphs:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p) + 1
        if current_len + p_len > max_chars and current:
            chunks.append('\n'.join(current))
            current = [p]
            current_len = p_len
            if len(chunks) >= max_chunks:
                break
        else:
            current.append(p)
            current_len += p_len

    if current:
        chunks.append('\n'.join(current))

    return chunks


def _call_api(
    client: OpenAI,
    text: str,
    num_questions: int,
    difficulty_instruction: str,
    type_instruction: str,
    subject_instruction: str,
    lang_instruction: str,
    model: str,
) -> list[Question]:
    """单次调用 AI 接口生成题目，含 prompt 构建和响应解析。"""
    user_prompt = (
        f"以下是一段文本内容，请根据它生成 {num_questions} 道题。\n\n"
        f"{difficulty_instruction}\n\n"
        f"{type_instruction}\n\n"
        f"{subject_instruction}\n\n"
        f"{lang_instruction}\n\n"
        f"--- 文本开始 ---\n"
        f"{text}\n"
        f"--- 文本结束 ---\n"
    )

    max_tokens = min(4096 + num_questions * 300, 16384)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=max_tokens,
        )
    except Exception as e:
        raise RuntimeError(f"调用 AI 接口失败: {e}")

    raw = response.choices[0].message.content or ""
    return _parse_response(raw)


def generate_questions(
    text: str,
    num_questions: int = 5,
    difficulty: int = 3,
    subject: str = "不限（通用）",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "gpt-4o-mini",
    language: str = "zh",
    question_types: str = "choice",  # "choice" 或 "mixed"
    progress_callback: Optional[Callable[[str], None]] = None,
) -> list[Question]:
    """根据文本生成题目。

    Args:
        text: 输入文本内容
        num_questions: 生成题目数量 (1-20)
        difficulty: 难度级别 (1-5, 1=最简单, 5=最困难)
        subject: 学科方向（影响出题风格和术语使用）
        api_key: OpenAI API Key (None 则从环境变量读取)
        base_url: API 地址 (用于代理或国内兼容接口)
        model: 模型名称
        language: "zh" 生成中文题, "en" 生成英文题
        question_types: "choice" 仅选择题, "mixed" 混合题型（选择+判断+填空）

    Returns:
        Question 对象列表

    Raises:
        ValueError: 文本太短或 API 调用失败
    """
    if len(text.strip()) < 50:
        raise ValueError("文本内容太短（少于 50 字符），无法生成题目。请上传更长的文档。")

    num_questions = max(1, min(50, num_questions))

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=120.0,
    )

    lang_instruction = (
        "请使用中文出题，题目、选项、解析都用中文。"
        if language == "zh"
        else "Please generate questions in English."
    )

    # 难度指令
    difficulty = max(1, min(5, difficulty))
    difficulty_instruction = DIFFICULTY_PROMPTS.get(difficulty, DIFFICULTY_PROMPTS[3])

    # 题型指令
    type_instruction = (
        "请全部生成选择题（choice 类型），不要生成判断题或填空题。"
        if question_types == "choice"
        else "请混合使用选择题(choice)、判断题(true_false)和填空题(fill_blank)三种题型，每种题型至少出 1 道，让题目类型丰富多样。"
    )

    # 学科指令
    if subject != "不限（通用）":
        subject_instruction = f"【学科方向：{subject}】请按{subject}学科风格出题，使用该学科的专业术语和常见题型。"
    else:
        subject_instruction = ""

    # ── 大文档分段出题 ──
    MAX_CHARS = 8000
    if len(text) <= MAX_CHARS:
        if progress_callback:
            progress_callback("正在生成题目...")
        return _call_api(client, text, num_questions,
                         difficulty_instruction, type_instruction,
                         subject_instruction, lang_instruction, model)

    chunks = _chunk_text(text, MAX_CHARS)
    num_chunks = len(chunks)
    per_chunk = max(1, ceil(num_questions / num_chunks))

    if progress_callback:
        progress_callback(f"文档较长，已分为 {num_chunks} 段处理...")

    all_questions: list[Question] = []
    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(f"正在处理第 {i + 1}/{num_chunks} 段...")
        chunk_qs = _call_api(client, chunk, per_chunk,
                             difficulty_instruction, type_instruction,
                             subject_instruction, lang_instruction, model)
        all_questions.extend(chunk_qs)

    if len(all_questions) > num_questions:
        all_questions = all_questions[:num_questions]

    return all_questions


def _repair_json(raw: str) -> str:
    """修复 LLM 返回中常见的 JSON 格式问题。"""
    s = raw.strip()
    result = []
    i = 0
    n = len(s)
    in_double = False
    in_single = False

    while i < n:
        ch = s[i]

        # Handle escape sequences inside strings
        if ch == '\\' and (in_double or in_single):
            if in_single and i + 1 < n and s[i + 1] == "'":
                result.append("'")
                i += 2
                continue
            result.append(ch)
            i += 1
            if i < n:
                result.append(s[i])
                i += 1
            continue

        # Handle // comments (outside strings only, skip URLs like http://)
        if not in_double and not in_single and ch == '/' and i + 1 < n and s[i + 1] == '/':
            if i > 0 and s[i - 1] == ':':
                result.append(ch)
                i += 1
                continue
            while i < n and s[i] != '\n':
                i += 1
            continue

        # Handle # comments (outside strings only)
        if not in_double and not in_single and ch == '#':
            is_comment = i == 0 or s[i - 1] in ' \t\n\r,{['
            if is_comment:
                while i < n and s[i] != '\n':
                    i += 1
                continue

        # Toggle double-quote state
        if ch == '"' and not in_single:
            in_double = not in_double
            result.append(ch)
            i += 1
            continue

        # Convert single quotes to double quotes
        if ch == "'" and not in_double:
            in_single = not in_single
            result.append('"')
            i += 1
            continue

        # Remove trailing commas (outside strings)
        if not in_double and not in_single and ch == ',':
            j = i + 1
            while j < n and s[j] in ' \t\n\r':
                j += 1
            if j < n and s[j] in ']}':
                i += 1
                continue

        result.append(ch)
        i += 1

    return ''.join(result)


def _parse_response(raw: str) -> list[Question]:
    """解析 AI 返回的 JSON 字符串为 Question 对象列表"""
    # 尝试从 ```json ... ``` 中提取
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1).strip()

    # 修复常见 JSON 格式问题后再尝试解析
    raw = _repair_json(raw)

    # 尝试直接解析
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # 尝试查找最外层 [...] 并修复
        bracket_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if bracket_match:
            try:
                data = json.loads(bracket_match.group(0))
            except json.JSONDecodeError:
                raise ValueError(
                    f"AI 返回格式异常，无法解析。原始返回:\n{raw[:500]}"
                )
        else:
            raise ValueError(
                f"AI 返回格式异常，未找到 JSON 数组。原始返回:\n{raw[:500]}"
            )

    questions = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            logger.warning("第 %d 项不是合法对象，已跳过", idx + 1)
            continue

        q_type = item.get("question_type", "choice")
        question_text = (item.get("question") or "").strip()

        # 跳过没有题目的空项
        if not question_text:
            logger.warning("第 %d 项缺少题目文本，已跳过", idx + 1)
            continue

        # 构造 Question 对象
        q = Question(
            question=question_text,
            question_type=q_type,
            options=item.get("options", []),
            correct_index=item.get("correct_index", 0),
            correct_answer=item.get("correct_answer", ""),
            acceptable_answers=item.get("acceptable_answers", []),
            explanation=item.get("explanation", ""),
        )

        # ── 数据完整性校验 ──
        valid = True
        if q.question_type in ("choice", "true_false"):
            if not q.options:
                logger.warning("第 %d 题「%s」缺少选项，已跳过", idx + 1, q.question[:30])
                valid = False
            elif q.correct_index < 0 or q.correct_index >= len(q.options):
                logger.warning(
                    "第 %d 题 correct_index=%d 超出选项范围(0-%d)，已重置为 0",
                    idx + 1, q.correct_index, len(q.options) - 1,
                )
                q.correct_index = 0
        elif q.question_type == "fill_blank":
            if not q.correct_answer:
                logger.warning("第 %d 题「%s」缺少正确答案，已跳过", idx + 1, q.question[:30])
                valid = False

        if valid:
            questions.append(q)

    if not questions:
        raise ValueError("AI 返回的题目数据全部无效，请重新生成。")

    return questions
