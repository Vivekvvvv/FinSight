# -*- coding: utf-8 -*-
"""phase9_minimal_release_smoke 中途崩溃时必须回收它 Popen 的后端进程：
api()/urlopen 只兜 HTTPError，URLError/超时穿透后脚本直接挂——
此前 proc.terminate 只在脚本末尾执行，崩溃留下占 :8899 的孤儿 uvicorn，
后续每次 smoke 都绑不上端口。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "phase9_minimal_release_smoke.py"
SMOKE_PORT = 8899

# 伪装成 `python -m uvicorn`：/health 返回 200（让脚本判定 ready），
# 其余请求挂起——脚本 GET /api/me 超时抛 URLError，走中途崩溃路径。
# handle_request 循环 + stop-server 哨兵文件保证测试自身能回收假后端，
# 即使被测脚本失败也不留孤儿。
FAKE_UVICORN = '''
import sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

port = 8899
for i, arg in enumerate(sys.argv):
    if arg == "--port" and i + 1 < len(sys.argv):
        port = int(sys.argv[i + 1])
stop_file = Path(__file__).with_name("stop-server")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            time.sleep(60)
    do_POST = do_GET
    def log_message(self, *args):
        pass

httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
httpd.daemon_threads = True
httpd.timeout = 0.5
deadline = time.time() + 180
while time.time() < deadline and not stop_file.exists():
    httpd.handle_request()
'''


def _health_up() -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{SMOKE_PORT}/health", timeout=1
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.fixture()
def fake_uvicorn_dir(tmp_path):
    (tmp_path / "uvicorn.py").write_text(FAKE_UVICORN, encoding="utf-8")
    yield tmp_path
    # 测试侧兜底：若被测脚本漏杀，哨兵让假后端 handle_request 循环退出
    (tmp_path / "stop-server").touch()
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{SMOKE_PORT}/health", timeout=1
        )
    except Exception:
        pass
    deadline = time.time() + 5
    while _health_up() and time.time() < deadline:
        time.sleep(0.2)


def test_mid_run_crash_reaps_spawned_backend(fake_uvicorn_dir):
    if _health_up():
        pytest.skip(f"port {SMOKE_PORT} already occupied by another process")

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=str(fake_uvicorn_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={**os.environ},
    )

    # 脚本在 /api/me 处超时崩溃——异常穿透，退出码非 0
    assert result.returncode != 0, (
        f"expected smoke to crash mid-run, got rc=0:\n{result.stdout[-800:]}"
    )
    assert "backend-startup" in result.stdout

    # 关键断言：崩溃退出后 :8899 不再被占用（孤儿已被 atexit 回收）
    deadline = time.time() + 10
    while _health_up() and time.time() < deadline:
        time.sleep(0.25)
    assert not _health_up(), "orphaned backend still listening on :8899 after smoke crash"
