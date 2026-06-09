"""
侧边栏渲染模块 — 服务商选择、API Key、题目配置、暗黑切换
"""
import os
import streamlit as st


def _env_path() -> str:
    """返回 .env 文件的绝对路径"""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def load_api_key() -> str:
    """从 .env 文件加载上一次保存的 API Key"""
    env_file = _env_path()
    if not os.path.exists(env_file):
        return ""
    try:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("QUIZ_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def save_api_key(key: str):
    """将 API Key 持久化写入 .env 文件"""
    if not key.strip():
        return
    env_file = _env_path()
    lines: list[str] = []
    found = False
    if os.path.exists(env_file):
        try:
            with open(env_file, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            pass
    for i, line in enumerate(lines):
        if line.startswith("QUIZ_API_KEY="):
            lines[i] = f'QUIZ_API_KEY="{key}"\n'
            found = True
            break
    if not found:
        lines.append(f'QUIZ_API_KEY="{key}"\n')
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)


def render_sidebar() -> dict:
    """渲染侧边栏配置区域，返回用户选择的各项配置。

    Returns:
        dict with keys: api_key, base_url, model, num_questions, difficulty,
                        language, question_type_mode
    """
    st.title("⚙️ 配置")

    # 服务商选择
    provider = st.selectbox(
        "AI 服务商",
        options=["DeepSeek（推荐，注册送额度）", "OpenAI", "自定义"],
        index=0,
        help="DeepSeek 注册即送额度，价格便宜，兼容 OpenAI 格式。",
    )

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

    # 根据服务商选择环境变量
    if provider == "DeepSeek（推荐，注册送额度）":
        env_key = os.getenv("DEEPSEEK_API_KEY", "")
        default_base_url = os.getenv("DEEPSEEK_BASE_URL", defaults["base_url"])
    elif provider == "OpenAI":
        env_key = os.getenv("OPENAI_API_KEY", "")
        default_base_url = os.getenv("OPENAI_BASE_URL", defaults["base_url"])
    else:
        env_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        default_base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or defaults["base_url"]

    # 优先用持久化的 key
    saved_key = load_api_key()
    default_api_key = saved_key or env_key

    # API Key 输入
    api_key = st.text_input(
        defaults["key_label"],
        type="password",
        value=default_api_key,
        help=defaults["key_help"],
        placeholder=defaults["key_placeholder"],
    )

    # Key 变化时自动保存到 .env
    if "saved_api_key" not in st.session_state:
        st.session_state.saved_api_key = saved_key
    if api_key and api_key != st.session_state.saved_api_key:
        save_api_key(api_key)
        st.session_state.saved_api_key = api_key

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

    # 学科选择
    subject = st.selectbox(
        "学科方向",
        options=[
            "不限（通用）", "数学", "物理", "化学", "生物",
            "历史", "地理", "政治", "语文/文学",
            "英语/外语", "计算机/编程", "经济学", "心理学",
        ],
        index=0,
        help="选择学科后，AI 会使用对应领域的术语和出题风格",
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

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "num_questions": num_questions,
        "difficulty": difficulty,
        "subject": subject,
        "language": language,
        "question_type_mode": question_type_mode,
    }
