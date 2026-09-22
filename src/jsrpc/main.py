# -*- coding: UTF-8 -*-
"""进程入口：uvicorn 单进程单事件循环，WS 服务经应用 lifespan 同循环运行。"""
from __future__ import annotations

import uvicorn
from loguru import logger

from .config import Config
from .http_server import create_app

# SIGINT/SIGTERM 后在途请求的等待上限（秒）：uvicorn 默认为 None 即无限等待，
# 必须显式设置，否则空闲 keep-alive 之外的慢请求又会拖住关机。
GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS = 10.0


def main() -> None:
    config = Config.from_env()
    app = create_app(config)

    logger.info(f"http server on http://{config.http_host}:{config.http_port}")
    uvicorn.run(
        app,
        host=config.http_host,
        port=config.http_port,
        # 显式 h11（非 auto）：auto 会自动优先探测 httptools，
        # 而 httptools 0.8.0 在 Python 3.14 下收下请求却永不解析（实测 h11 即时应答）。
        http="h11",
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
    )


if __name__ == "__main__":
    main()
