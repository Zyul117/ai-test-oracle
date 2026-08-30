"""
测试共享 fixture

mock_server 用后台线程起本地 HTTP 服务，让 HTTP 执行层的测试
不依赖任何外部环境，CI 里也能跑。
"""

import sys
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest

# 让 mock_server.py（在仓库根目录）可被导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mock_server import MockHandler   # noqa: E402


@pytest.fixture(scope="session")
def mock_server():
    """启动本地 mock API，返回 base_url；session 结束自动关停"""
    # 端口传 0 让系统分配空闲端口，避免与已占用的 8000 冲突
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    host, port = server.server_address

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://{host}:{port}"

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
