"""
AI 出题模块 - 调用 LLM 根据文本内容自动生成选择题
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

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


def generate_questions(
    text: str,
    num_questions: int = 5,
    difficulty: int = 3,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "gpt-4o-mini",
    language: str = "zh",
    question_types: str = "choice",  # "choice" 或 "mixed"
) -> list[Question]:
    """根据文本生成题目。

    Args:
        text: 输入文本内容
        num_questions: 生成题目数量 (1-20)
        difficulty: 难度级别 (1-5, 1=最简单, 5=最困难)
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

    # 智能截断：短文本全量用，长文本取头+中+尾的段落采样
    MAX_CHARS = 8000
    if len(text) <= MAX_CHARS:
        truncated = text
    else:
        paragraphs = [p for p in text.split('\n') if p.strip()]
        # 取开头段落（~40%）+ 尾部段落（~30%），中间均匀抽样
        head_end = int(len(paragraphs) * 0.4)
        tail_start = int(len(paragraphs) * 0.7)
        sampled = paragraphs[:head_end] + paragraphs[tail_start:]

        truncated = '\n'.join(sampled)
        if len(truncated) > MAX_CHARS:
            # 如果还是太长，从头截断到段落边界
            truncated = text[:MAX_CHARS]
            last_para = truncated.rfind('\n')
            if last_para > MAX_CHARS // 2:
                truncated = truncated[:last_para]

    user_prompt = (
        f"以下是一段文本内容，请根据它生成 {num_questions} 道题。\n\n"
        f"{difficulty_instruction}\n\n"
        f"{type_instruction}\n\n"
        f"{lang_instruction}\n\n"
        f"--- 文本开始 ---\n"
        f"{truncated}\n"
        f"--- 文本结束 ---\n"
    )

    # 根据题目数量动态调整输出 token，防止 JSON 被截断
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


def _repair_json(raw: str) -> str:
    """修复 LLM 返回中常见的 JSON 格式问题。"""
    repaired = raw.strip()
    # 1. 移除尾随逗号（数组/对象最后一个元素后的逗号）
    repaired = re.sub(r",\s*([\]}])", r"\1", repaired)
    # 2. 单引号键/值转双引号（保留字符串内的转义）
    repaired = re.sub(r"(?<!\\)'(?=[^:]+:)", '"', repaired)
    repaired = re.sub(r":\s*'(.*?)'(?=[,}\]])", lambda m: ': "' + m.group(1) + '"', repaired)
    # 3. 移除注释（// 或 # 风格，不在字符串内的）
    repaired = re.sub(r"(?<!:)\s*//[^\n]*", "", repaired)
    repaired = re.sub(r"(?<!:)\s*#[^\n]*", "", repaired)
    return repaired


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
