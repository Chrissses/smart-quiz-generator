---
name: quiz-generator
description: 智能出题系统 - AI Quiz Generator (Python/Streamlit, PDF/Word parsing, OpenAI-compatible LLM quiz generation)
---

# 智能出题系统 (AI Quiz Generator)

**Stack**: Python + Streamlit + OpenAI-compatible API + pdfplumber + python-docx + PyInstaller

## Project Structure

```
quiz-generator-source/
├── app.py                     # Streamlit 主入口 (thread-safe via queue.Queue)
├── run_app.py                 # PyInstaller 启动入口 (双击 exe 入口)
├── style.css                  # 暗黑主题 CSS
├── sample.txt                 # 示例文本
├── requirements.txt           # 运行依赖 (5个: streamlit, python-docx, pdfplumber, openai, python-dotenv)
├── requirements-build.txt     # 构建依赖 (pyinstaller)
├── pytest.ini                 # pytest 配置
├── 智能出题系统.spec           # PyInstaller spec (onedir, no console)
├── utils/
│   ├── file_parser.py         # 文件解析 (PDF/pdfplumber, DOCX/python-docx, TXT/MD)
│   └── question_gen.py        # AI 出题核心 (LLM调用, JSON修复, 文本截断)
├── ui/
│   ├── quiz.py                # 题目渲染 + 批改 + 导出 + 计时
│   └── sidebar.py             # 侧边栏配置 (服务商/API Key/参数)
└── tests/
    ├── test_file_parser.py    # 真实PDF解析测试
    ├── test_question_gen.py   # 出题模块单元测试
    └── test_integration.py    # 集成测试 (mock OpenAI)
```

## When to Use

Activate this skill when working on the smart-quiz-generator codebase — modifying features, fixing bugs, adding tests, or building the executable.

## Dev Commands

- **Run**: `streamlit run app.py`
- **Test**: `pytest -v` (configured via pytest.ini: `testpaths=tests`, `python_files=test_*.py`)
- **Build exe**: `pyinstaller 智能出题系统.spec` (output in `dist/智能出题系统/`)
- **Build & zip**: after pyinstaller, zip `dist/智能出题系统/` to `智能出题系统.zip`

## Code Conventions

### 1. Type Hints (MANDATORY)
Every function signature MUST have full type hints. No exceptions.

```python
def grade_fill_blank(q: Question, user_answer: str) -> tuple[bool, str, str]: ...
def generate_questions(text: str, num_questions: int = 5, difficulty: int = 3) -> list[Question]: ...
```

### 2. Question Dataclass (utils/question_gen.py)
```python
@dataclass
class Question:
    question: str = ""
    question_type: str = "choice"  # "choice" | "true_false" | "fill_blank"
    options: list[str] = field(default_factory=list)
    correct_index: int = 0        # 0-based for choice/true_false
    correct_answer: str = ""      # for fill_blank
    acceptable_answers: list[str] = field(default_factory=list)  # for fill_blank
    explanation: str = ""
```

### 3. Pure Functions (ui/quiz.py)
- `render_questions()` MUST NOT mutate the `user_answers` dict parameter
- Instead, return modified state for the caller to merge

### 4. Thread Safety (app.py)
Use `queue.Queue` for cross-thread communication:
```python
_gen_queue: queue.Queue = queue.Queue()
def _launch_generation(**kwargs):
    def _worker():
        try:
            questions = generate_questions(**kwargs)
            _gen_queue.put(("result", questions))
        except Exception as e:
            _gen_queue.put(("error", str(e)))
    threading.Thread(target=_worker, daemon=True).start()
```

### 5. .env Handling (ui/sidebar.py)
- READ: `dotenv_values(env_path).get("QUIZ_API_KEY", "")` — do NOT use `os.environ`
- WRITE: custom `save_api_key()` that parses/reconstructs the file line by line

### 6. JSON Repair (utils/question_gen.py)
`_repair_json()` uses a state machine approach (not fragile regex):
- States: `SEARCH, IN_STRING, ESCAPE`
- Extracts text between `[` and `]` brackets, handling escaped quotes
- Falls back to regex only as last resort

### 7. Text Truncation (utils/question_gen.py)
Before sending to LLM, truncate text uniformly:
- Target ~num_questions × 200 chars per sample
- Sample evenly across the text: `step = max(1, len(text) // samples_needed)`

### 8. Fill-Blank Grading (ui/quiz.py)
Use `difflib.SequenceMatcher` with 0.8 threshold for lenient matching:
```python
ratio = difflib.SequenceMatcher(None, user_answer, correct_answer).ratio()
if ratio >= 0.8:
    return True, ...
```

## Testing Patterns

### Mock OpenAI (tests/test_integration.py, tests/test_question_gen.py)
```python
from unittest.mock import MagicMock, patch

@patch("utils.question_gen.OpenAI")
def test_something(self, mock_openai):
    mock_instance = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"key": "value"}'
    mock_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_openai.return_value = mock_instance
```

### Real PDF Test (tests/test_file_parser.py)
- Uses `pdfplumber` on actual PDF bytes
- Create minimal PDF content inline for testing

## Difficulty Levels

| Level | Description |
|-------|-------------|
| 1 | 非常简单 - 原文直给 |
| 2 | 简单 - 原文明显知识点 |
| 3 | 适中 - 需要理解段落 |
| 4 | 较难 - 跨段落推理 |
| 5 | 困难 - 深层分析/批判性思维 |

## Build (PyInstaller)

- Spec file: `智能出题系统.spec` (onedir, no console)
- Hidden imports include: `streamlit.runtime.scriptrunner.magic_funcs`, all app modules, `dotenv`, `openai`, `pdfplumber`, `docx`
- Excludes: `tkinter`, `matplotlib`, `scipy`
- Entry point: `run_app.py` (not app.py)

## Key Imports Map

| Import Path | Module |
|---|---|
| `app.py` | Main entry |
| `utils.file_parser` | `parse_file()` |
| `utils.question_gen` | `Question`, `generate_questions()` |
| `ui.quiz` | `grade_choice`, `grade_fill_blank`, `render_questions`, `render_results` |
| `ui.sidebar` | `render_sidebar()`, `load_api_key()`, `save_api_key()` |
