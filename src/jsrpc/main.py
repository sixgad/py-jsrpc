# -*- coding: UTF-8 -*-
"""进程入口：单进程单事件循环同时运行 HTTP 与 WS 两个服务。"""
from __future__ import annotations

from loguru import logger

from .config import Config
from .http_server import create_app
from .registry import Registry
from .ws_server import start_ws_server


def main() -> None:
    config = Config.from_env()
    registry = Registry()
    app = create_app(config)

    @app.before_server_start
    async def _start_ws(_app, _loop):
        await start_ws_server(config, registry)

    logger.info(f"http server on http://{config.http_host}:{config.http_port}")
    # Sanic 25 的多进程管理器会在子进程按名字重新导入 app，破坏进程内共享的
    # 注册表与工厂模式；本项目模型即单进程，显式关闭多进程。
    app.run(
        host=config.http_host,
        port=config.http_port,
        debug=False,
        single_process=True,
    )


if __name__ == "__main__":
    main()
