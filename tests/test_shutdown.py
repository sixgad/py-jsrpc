# -*- coding: UTF-8 -*-
"""关机语义回归测试。

红基线（历史实测，见 spec 前置调查）：sanic 25.12.1 + Python 3.14 下，
停止时存在空闲 keep-alive 连接，进程需等 KEEP_ALIVE_TIMEOUT(120s) 才退出
（harness：RED@60s / GREEN@~100s）。

本测试在测试进程内程序化驱动 uvicorn 停止（SIGINT 处理器的等价入口
should_exit），携带一条已响应完毕、故意不关闭的 keep-alive 连接，
断言停止在限时内完成且 WS 监听端口随后释放。
"""
from __future__ import annotations

import socket
import threading
import time

import uvicorn

from jsrpc.config import Config
from jsrpc.http_server import create_app
from jsrpc.main import GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS

STOP_BUDGET_SECONDS = 12.0


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"port {port} never came up")


def _port_closed(port: int, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                time.sleep(0.1)
        except OSError:
            return True
    return False


def test_shutdown_with_idle_keepalive_connection_is_bounded() -> None:
    http_port, ws_port = _free_port(), _free_port()
    config = Config(
        http_host="127.0.0.1", http_port=http_port, ws_host="127.0.0.1", ws_port=ws_port
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(config),
            host=config.http_host,
            port=config.http_port,
            http="h11",
            timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
            log_level="warning",
        )
    )
    thread_errors: list[BaseException] = []

    def _run() -> None:
        # 捕获线程内异常：否则 shutdown 链抛异常导致的线程早退会被
        # “is_alive 为假 + elapsed 极小”的组合假象放行
        try:
            server.run()
        except BaseException as exc:  # noqa: BLE001 - 测试侧必须全量捕获后断言
            thread_errors.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    keepalive: socket.socket | None = None
    try:
        _wait_port(http_port)
        _wait_port(ws_port)

        # 一条完成响应、保持打开的空闲 keep-alive 连接（浏览器连接池的稳态）
        keepalive = socket.create_connection(("127.0.0.1", http_port))
        keepalive.settimeout(5)
        keepalive.sendall(
            b"GET /send?group=g HTTP/1.1\r\nHost: x\r\nConnection: keep-alive\r\n\r\n"
        )
        body = b""
        while b"error" not in body:  # 读完响应体再进入空闲态
            chunk = keepalive.recv(4096)
            assert chunk, "server closed keepalive connection prematurely"
            body += chunk

        started = time.monotonic()
        server.should_exit = True  # SIGINT 处理器置位的同一停止入口
        thread.join(timeout=STOP_BUDGET_SECONDS)
        elapsed = time.monotonic() - started

        assert not thread.is_alive(), (
            f"shutdown did not finish within {STOP_BUDGET_SECONDS}s "
            f"(sanic-era hang would need ~120s)"
        )
        assert thread_errors == [], f"server.run raised during shutdown: {thread_errors!r}"
        assert elapsed <= STOP_BUDGET_SECONDS
        assert _port_closed(ws_port), "ws listener still reachable after shutdown"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if keepalive is not None:
            keepalive.close()
