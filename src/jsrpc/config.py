# -*- coding: UTF-8 -*-
"""服务配置：环境变量覆盖，默认值与迁移前保持一致。"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name, "")
    if not raw:
        return default
    value = int(raw)
    if not 0 < value < 65536:
        raise ValueError(f"{name} 端口非法: {value}")
    return value


@dataclass(frozen=True)
class Config:
    http_host: str
    http_port: int
    ws_host: str
    ws_port: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            http_host=_env_str("JSRPC_HTTP_HOST", "127.0.0.1"),
            http_port=_env_int("JSRPC_HTTP_PORT", 5000),
            ws_host=_env_str("JSRPC_WS_HOST", "127.0.0.1"),
            ws_port=_env_int("JSRPC_WS_PORT", 6789),
        )
