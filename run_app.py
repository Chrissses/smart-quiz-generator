"""
启动入口 - 双击此 exe 启动智能出题系统
"""
import io
import os
import socket
import sys
import time
import urllib.request
import webbrowser
from threading import Thread

# 解决中文输出到控制台的编码问题
try:
    if sys.stdout is not None and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and "1252" in sys.stdout.encoding.upper():
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr is not None and hasattr(sys.stderr, 'encoding') and sys.stderr.encoding and "1252" in sys.stderr.encoding.upper():
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 切换到项目目录 ──────────────────────────────────────
if getattr(sys, 'frozen', False):
    basedir = os.path.dirname(sys.executable)
    data_dir = os.path.join(basedir, '_internal')
    if not os.path.exists(os.path.join(basedir, 'app.py')) and os.path.exists(os.path.join(data_dir, 'app.py')):
        basedir = data_dir
else:
    basedir = os.path.dirname(os.path.abspath(__file__))
os.chdir(basedir)

# 日志写在用户目录（确保可写）
LOG_DIR = os.path.join(os.path.expanduser("~"), ".智能出题系统")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "启动日志.txt")

# ── 修复 PyInstaller 打包后 streamlit 版本检测 ──────────
if getattr(sys, 'frozen', False):
    import importlib.metadata as _md
    _orig_version = _md.version
    def _patched_version(name):
        if name == 'streamlit':
            return '1.57.0'
        return _orig_version(name)
    _md.version = _patched_version

# 加载 .env（如果有）
from dotenv import load_dotenv
load_dotenv()

from streamlit.web import cli as stcli


def find_free_port(start: int = 8501, max_attempts: int = 100) -> int:
    """用 SO_REUSEADDR + bind 检测可用端口（不长期持有，仅探测）。
    返回后在 Streamlit bind 之前仍有微小竞态，但概率极低。"""
    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"无法在端口 {start}-{start + max_attempts - 1} 范围内找到可用端口")


def http_health_check(port: int, timeout: int = 40) -> bool:
    """用 HTTP GET 检查 Streamlit 是否真正就绪（不只是端口开放）。"""
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            # Streamlit 返回 200 或 302（重定向到 /）
            if resp.status in (200, 302):
                return True
        except (urllib.error.URLError, socket.timeout, ConnectionError):
            pass
        time.sleep(0.5)
    return False


def open_browser_when_ready(port: int):
    """等待 Streamlit HTTP 就绪后打开浏览器。"""
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[信息] 开始健康检查端口 {port}\n")

    if http_health_check(port):
        url = f"http://localhost:{port}"
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[信息] Server 就绪，打开浏览器: {url}\n")
        webbrowser.open_new(url)
    else:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[错误] Server 在端口 {port} 启动超时\n")


if __name__ == "__main__":
    try:
        # 1. 找可用端口（仅探测，不持有）
        port = find_free_port()

        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(f"[信息] 使用端口: {port}\n")

        # 2. 后台线程等待 Server HTTP 就绪后打开浏览器
        Thread(target=open_browser_when_ready, args=(port,), daemon=True).start()

        # 3. 启动 Streamlit
        sys.argv = [
            "streamlit",
            "run", "app.py",
            "--server.headless", "true",
            "--server.address", "127.0.0.1",
            f"--server.port", str(port),
            "--global.developmentMode", "false",
            "--browser.gatherUsageStats", "false",
        ]
        sys.exit(stcli.main())

    except Exception as e:
        import traceback
        import ctypes
        err_msg = f"启动失败: {e}\n{traceback.format_exc()}"
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(err_msg + "\n")
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                f"智能出题系统启动失败，请查看日志了解详情：\n{LOG_PATH}\n\n错误信息: {e}",
                "智能出题系统 - 启动错误",
                0x10,  # MB_ICONERROR
            )
        except Exception:
            pass
        sys.exit(1)
