# -*- coding: UTF-8 -*-
"""HTTP 入口：/send 路由把一次 GET 转成一次 WebSocket RPC 成功往返的 JSON 结果。

成功路径报文与协议参考实现逐字段一致；失败路径（缺参、WS 服务不可达、
目标客户端失效、超时、非 JSON 回包）统一返回 {"error": ...}（状态码 200），
不挂起、不 5xx。错误字符串共 6 条，是对外契约的一部分，改动须过端到端测试
或在 spec 的枚举契约中登记。

WS 服务与应用共享事件循环：lifespan 启动阶段拉起并持有句柄，
关闭阶段 close（对活跃连接发 1001、拒新连）并等待全部连接处理器退出。
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from .config import Config
from .registry import Registry
from .ws_server import start_ws_server

# 等待 js 客户端回包的兜底超时（秒）：目标连接失效等边缘场景不再无限挂起
RPC_TIMEOUT_SECONDS = 30.0


class CompatJSONResponse(JSONResponse):
    """保持 sanic 时代的 wire 字节兼容：非 ASCII 转义为 \\uXXXX。

    starlette 默认 ensure_ascii=False，同一 JSON 值的字节表示不同；
    本项目返回值常含中文，按字节契约对齐迁移前行为。
    """

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=True,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


def _query_args(request: Request) -> dict[str, str]:
    """同名多值参数后者覆盖前者，与 sanic 时代手工字典语义一致。"""
    return {key: value for key, value in request.query_params.multi_items()}


def create_app(config: Config, rpc_timeout: float = RPC_TIMEOUT_SECONDS) -> FastAPI:
    registry = Registry()
    invoke_url = f"ws://{config.ws_host}:{config.ws_port}/invoke?group="

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        ws_server = await start_ws_server(config, registry)
        app.state.ws_server = ws_server
        try:
            yield
        finally:
            ws_server.close()
            await ws_server.wait_closed()
            logger.info("ws server closed")

    # 关闭 FastAPI 默认文档面（/docs /redoc /openapi.json）：
    # 本项目对外契约只有 /send 一个 GET 端点，不引入迁移前不存在的可浏览表面。
    app = FastAPI(
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/send")
    async def send(request: Request) -> JSONResponse:
        args = _query_args(request)
        if "action" not in args:
            return CompatJSONResponse({"error": "need action"})
        if "group" not in args:
            return CompatJSONResponse({"error": "need group"})
        group = args.pop("group")
        try:
            async with connect(invoke_url + quote(group)) as ws:
                await ws.send(json.dumps(args))
                raw = await asyncio.wait_for(ws.recv(), timeout=rpc_timeout)
        except asyncio.TimeoutError:
            logger.warning(f"rpc timeout group={group!r} action={args.get('action')!r}")
            return CompatJSONResponse({"error": "timeout waiting for webclient response"})
        except ConnectionClosed:
            return CompatJSONResponse({"error": "ws connection closed before response"})
        except OSError:
            return CompatJSONResponse({"error": "cannot reach ws server"})
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return CompatJSONResponse({"error": "invalid json from webclient"})
        return CompatJSONResponse(payload)

    return app
