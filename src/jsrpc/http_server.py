# -*- coding: UTF-8 -*-
"""HTTP 入口：/send 路由把一次 GET 转成一次 WebSocket RPC 往返。

成功路径报文与迁移前一致；失败路径（缺参、WS 服务不可达、目标客户端
失效、超时、非 JSON 回包）统一返回 {"error": ...}，不挂起、不 500。
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

from loguru import logger
from sanic import Sanic, response
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from .config import Config

# 等待 js 客户端回包的兜底超时（秒）：目标连接失效等边缘场景不再无限挂起
RPC_TIMEOUT_SECONDS = 30.0


def create_app(config: Config, rpc_timeout: float = RPC_TIMEOUT_SECONDS) -> Sanic:
    app = Sanic("jsrpc")
    invoke_url = f"ws://{config.ws_host}:{config.ws_port}/invoke?group="

    @app.route("/send", methods=["GET"])
    async def send(request):
        args = {key: value for key, value in request.query_args}
        if "action" not in args:
            return response.json({"error": "need action"})
        if "group" not in args:
            return response.json({"error": "need group"})
        group = args.pop("group")
        try:
            async with connect(invoke_url + quote(group)) as ws:
                await ws.send(json.dumps(args))
                raw = await asyncio.wait_for(ws.recv(), timeout=rpc_timeout)
        except asyncio.TimeoutError:
            logger.warning(f"rpc timeout group={group!r} action={args.get('action')!r}")
            return response.json({"error": "timeout waiting for webclient response"})
        except ConnectionClosed:
            return response.json({"error": "ws connection closed before response"})
        except OSError:
            return response.json({"error": "cannot reach ws server"})
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return response.json({"error": "invalid json from webclient"})
        return response.json(payload)

    return app
