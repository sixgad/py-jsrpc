# -*- coding: UTF-8 -*-
"""WebSocket 服务：一对多连接注册与 RPC 消息路由（websockets 新版 asyncio API）。

协议与迁移前逐字段一致：
- js 客户端注册:  /register?group=<g>&clientId=<id>
- 调用方接入:    /invoke?group=<g>
- apiclient 消息含 action -> 随机选组内 webclient，附加 __uuid_seq__ 后转发
- webclient 消息含 status -> 按 __uuid_seq__ 找回 apiclient，去掉该字段后原样转发
失败路径（未知路径、组内无客户端、目标连接已断、seq 无法找回、非 JSON 帧）
统一为日志告警或结构化错误报文，不再抛异常杀死连接。
"""
from __future__ import annotations

import json
from functools import partial
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import websockets
from loguru import logger
from websockets.asyncio.server import Server, ServerConnection
from websockets.exceptions import ConnectionClosed

from .config import Config
from .registry import Registry

# 未知路径/缺参数的关闭码：4000-4999 为应用自定义区间
CLOSE_BAD_REQUEST = 4001


def _first_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    return values[0] if values else None


def _parse_registration(request_line: str) -> tuple[str | None, str | None, str | None]:
    """从请求路径解析 (role, group, clientId)；无法识别时返回全 None。"""
    parsed = urlparse(request_line)
    params = parse_qs(parsed.query)
    if parsed.path == "/register":
        group = _first_param(params, "group")
        client_id = _first_param(params, "clientId")
        if group and client_id:
            return "webclient", group, client_id
    elif parsed.path == "/invoke":
        group = _first_param(params, "group")
        if group:
            return "apiclient", group, uuid4().hex
    return None, None, None


async def _route_message(
    registry: Registry,
    ws: ServerConnection,
    role: str,
    group: str,
    client_id: str,
    raw: Any,
) -> None:
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"drop non-json frame from {role} of group {group!r}")
        return
    if not isinstance(message, dict):
        logger.warning(f"drop non-object frame from {role} of group {group!r}")
        return

    # apiclient 发起调用：随机派给组内一个 js 客户端
    if "action" in message and role == "apiclient":
        target = registry.pick_webclient(group)
        if target is None:
            await ws.send(json.dumps({"error": f"no webclient registered for group {group!r}"}))
            return
        message["__uuid_seq__"] = client_id
        try:
            await target.send(json.dumps(message))
        except ConnectionClosed:
            await ws.send(json.dumps({"error": f"webclient of group {group!r} is gone"}))

    # webclient 回传结果：按 seq 送回发起调用的 apiclient
    if "status" in message and role == "webclient":
        seq = message.pop("__uuid_seq__", None)
        api = registry.get_apiclient(group, seq) if isinstance(seq, str) else None
        if api is None:
            logger.warning(f"drop orphan response seq={seq!r} from group {group!r}")
            return
        try:
            await api.send(json.dumps(message))
        except ConnectionClosed:
            # HTTP 调用方已断开（超时/取消）：丢弃回包，不能牵连健康的 js 连接
            logger.warning(f"apiclient for seq={seq!r} gone, response dropped")


async def _handle_connection(registry: Registry, ws: ServerConnection) -> None:
    request_line = ws.request.path if ws.request else ""
    role, group, client_id = _parse_registration(request_line)
    if role is None:
        await ws.close(
            code=CLOSE_BAD_REQUEST,
            reason="need /register?group=<g>&clientId=<id> or /invoke?group=<g>",
        )
        return

    if role == "webclient":
        registry.register_webclient(group, client_id, ws)
        logger.info(f"webclient registered group={group!r} clientId={client_id}")
    else:
        registry.register_apiclient(group, client_id, ws)
        logger.info(f"apiclient registered group={group!r} clientId={client_id}")
    try:
        async for raw in ws:
            logger.info(f"recv from {role} of group {group!r}: {raw}")
            await _route_message(registry, ws, role, group, client_id, raw)
    finally:
        if role == "webclient":
            registry.unregister_webclient(group, client_id, ws)
            logger.info(f"webclient unregistered group={group!r} clientId={client_id}")
        else:
            registry.unregister_apiclient(group, client_id)
            logger.info(f"apiclient unregistered group={group!r} clientId={client_id}")


async def start_ws_server(config: Config, registry: Registry) -> Server:
    server = await websockets.asyncio.server.serve(
        partial(_handle_connection, registry),
        config.ws_host,
        config.ws_port,
    )
    logger.info(f"ws server on ws://{config.ws_host}:{config.ws_port}")
    return server
