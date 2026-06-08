# 📝 智能出题系统 - AI Quiz Generator

上传文档（PDF / Word / 纯文本 / Markdown），AI 自动生成选择题、判断题和填空题，帮你快速检验学习成果。

## ✨ 功能

- **多种文件格式** — 支持 PDF、Word (.docx)、纯文本 (.txt)、Markdown
- **三种题型** — 选择题（4 选 1）、判断题（正确/错误）、填空题
- **多模态 AI** — 支持 DeepSeek、OpenAI 等主流模型
- **难度可调** — 1~5 级难度，从原文直给到深层推理
- **暗黑主题** — 护眼暗色界面，长时间使用不疲劳
- **一键运行** — 打包为 Windows exe，双击即用

## 🚀 快速开始

### 方式一：直接运行（需要 Python）

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 方式二：打包为 exe

```bash
pip install pyinstaller
pyinstaller --onedir --name="智能出题系统" --noconsole ^
  --add-data="app.py;." --add-data="style.css;." --add-data="sample.txt;." ^
  --add-data="utils;utils" --collect-data="streamlit" --copy-metadata="streamlit" ^
  --hidden-import="streamlit.runtime.scriptrunner.magic_funcs" ^
  --exclude-module="tkinter" --exclude-module="matplotlib" run_app.py
```

产物在 `dist/智能出题系统/` 目录。

### 方式三：直接下载 exe

从 [Releases]() 页面下载最新版本，双击运行即可。

## 🔧 使用说明

1. 启动后在左侧边栏选择 AI 服务商并填入 API Key
2. 上传你的学习资料（PDF / Word / 文本）
3. 设置题目数量、难度和题型
4. 点击「开始出题」等待 AI 生成
5. 在线作答并查看详细解析

## 📦 项目结构

```
quiz-generator-source/
├── app.py              # Streamlit 主应用
├── run_app.py          # 启动入口（双击 exe 入口）
├── style.css           # 暗黑主题样式
├── sample.txt          # 示例文本
├── requirements.txt    # Python 依赖
├── utils/
│   ├── __init__.py
│   ├── file_parser.py  # 文件解析模块（PDF/Word/文本）
│   └── question_gen.py # AI 出题模块
└── .gitignore
```

## ⚙️ 技术栈

- [Streamlit](https://streamlit.io/) — Web UI 框架
- [OpenAI API](https://platform.openai.com/) / [DeepSeek API](https://platform.deepseek.com/) — AI 模型
- [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF 解析
- [python-docx](https://github.com/python-openxml/python-docx) — Word 文档解析
- [PyInstaller](https://pyinstaller.org/) — exe 打包
