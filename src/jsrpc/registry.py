# -*- coding: UTF-8 -*-
"""进程内连接注册表：group -> clientId -> 服务端连接对象。

注册表不感知传输层细节（websockets 连接对象的类型以别名表达），
只负责登记、注销与按组选取；"组内无可用客户端"以返回 None 表达，
由调用方（WS 层）翻译成结构化错误，注册表本身不抛异常。
"""
from __future__ import annotations

import random
from typing import Any

# websockets.asyncio.server.ServerConnection；以别名保持本模块与传输层解耦
ServerWebSocket = Any


class Registry:
    """维护两类连接：js 客户端（webclient）与 HTTP 调用代理（apiclient）。"""

    def __init__(self) -> None:
        self._webclients: dict[str, dict[str, ServerWebSocket]] = {}
        self._apiclients: dict[str, dict[str, ServerWebSocket]] = {}

    def register_webclient(self, group: str, client_id: str, ws: ServerWebSocket) -> None:
        self._webclients.setdefault(group, {})[client_id] = ws

    def register_apiclient(self, group: str, client_id: str, ws: ServerWebSocket) -> None:
        self._apiclients.setdefault(group, {})[client_id] = ws

    def unregister_webclient(
        self, group: str, client_id: str, ws: ServerWebSocket | None = None
    ) -> None:
        # 传入 ws 时按连接身份注销：clientId 重连后，迟到的旧连接不得误删新注册
        clients = self._webclients.get(group)
        if not clients:
            return
        if ws is not None and clients.get(client_id) is not ws:
            return
        clients.pop(client_id, None)

    def unregister_apiclient(self, group: str, client_id: str) -> None:
        self._apiclients.get(group, {}).pop(client_id, None)

    def pick_webclient(self, group: str) -> ServerWebSocket | None:
        """随机返回组内一个 js 客户端；组不存在或已空返回 None。"""
        clients = self._webclients.get(group)
        if not clients:
            return None
        return random.choice(list(clients.values()))

    def get_apiclient(self, group: str, client_id: str) -> ServerWebSocket | None:
        """按 seq 找回发起调用的 apiclient；不存在返回 None。"""
        return self._apiclients.get(group, {}).get(client_id)
