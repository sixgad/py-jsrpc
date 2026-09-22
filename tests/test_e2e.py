# -*- coding: UTF-8 -*-
"""端到端全链路测试。

子进程启动服务入口（与 jsrpc-server 同一 main），按 client.js 的线上报文
格式模拟 js 客户端，经 HTTP /send 公开接缝验证 RPC 全链路：
成功往返、动作失败透传、组内无客户端、缺参——协议不变的回归证明。
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from websockets.asyncio.client import connect

GROUP = "e2e-group"
CLIENT_TIME = "2026-09-22T00:00:00Z"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def _wait_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.1)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise RuntimeError(f"port {port} not ready in {timeout}s")


@pytest.fixture()
async def server() -> AsyncIterator[dict[str, int]]:
    """子进程启动服务入口，用环境变量注入空闲端口。"""
    http_port, ws_port = _free_port(), _free_port()
    env = {**os.environ, "JSRPC_HTTP_PORT": str(http_port), "JSRPC_WS_PORT": str(ws_port)}
    # 优先起真实的 jsrpc-server 控制台入口（回归 [project.scripts] 声明本身）；
    # 入口脚本不存在时退回等价的 -m 入口。
    script = Path(sys.executable).parent / (
        "jsrpc-server.exe" if os.name == "nt" else "jsrpc-server"
    )
    argv = [str(script)] if script.exists() else [sys.executable, "-m", "jsrpc"]
    proc = await asyncio.create_subprocess_exec(
        *argv,
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await _wait_port(http_port)
        await _wait_port(ws_port)
        yield {"http": http_port, "ws": ws_port}
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()


async def _fake_webclient(url: str, received: list[dict], ready: asyncio.Event) -> None:
    """模拟 client.js：注册后按线上格式应答（成功含 status/data，失败含 status/message）。"""
    async with connect(url) as ws:
        ready.set()
        async for raw in ws:
            request = json.loads(raw)
            received.append(request)
            seq = request.get("__uuid_seq__")
            action = request.get("action")
            if action == "clientTime":
                await ws.send(json.dumps({"status": 0, "data": CLIENT_TIME, "__uuid_seq__": seq}))
            else:
                await ws.send(
                    json.dumps(
                        {
                            "message": f"no action handler: {action} defined",
                            "status": -1,
                            "__uuid_seq__": seq,
                        }
                    )
                )


async def _send_with_client(server: dict[str, int], params: dict[str, str]) -> dict:
    """经 /send 发起 RPC；容忍服务端注册与 HTTP 到达之间的毫秒级竞态。"""
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{server['http']}", timeout=10
    ) as client:
        for _ in range(50):
            resp = await client.get("/send", params=params)
            assert resp.status_code == 200
            body = resp.json()
            if not (isinstance(body.get("error"), str) and "no webclient" in body["error"]):
                return body
            await asyncio.sleep(0.1)
    raise AssertionError(f"webclient never became reachable: {params}")


async def _spawn_client(server: dict[str, int]) -> tuple[asyncio.Task, list[dict]]:
    received: list[dict] = []
    ready = asyncio.Event()
    url = f"ws://127.0.0.1:{server['ws']}/register?group={GROUP}&clientId=c-1"
    task = asyncio.create_task(_fake_webclient(url, received, ready))
    await asyncio.wait_for(ready.wait(), timeout=10)
    return task, received


async def test_rpc_roundtrip_success(server: dict[str, int]) -> None:
    task, received = await _spawn_client(server)
    try:
        body = await _send_with_client(
            server, {"group": GROUP, "action": "clientTime", "x": "1"}
        )
    finally:
        task.cancel()
    # HTTP 响应：客户端回包去掉 __uuid_seq__ 后原样返回
    assert body["status"] == 0
    assert body["data"] == CLIENT_TIME
    assert "__uuid_seq__" not in body
    # 转发报文：action、额外参数、服务端附加的 __uuid_seq__，不含 group
    assert received[0]["action"] == "clientTime"
    assert received[0]["x"] == "1"
    assert isinstance(received[0]["__uuid_seq__"], str)
    assert "group" not in received[0]


async def test_unknown_action_failure_passthrough(server: dict[str, int]) -> None:
    task, _ = await _spawn_client(server)
    try:
        body = await _send_with_client(server, {"group": GROUP, "action": "nope"})
    finally:
        task.cancel()
    assert body["status"] == -1
    assert "no action handler: nope defined" in body["message"]
    assert "__uuid_seq__" not in body


async def test_group_without_webclient_returns_error(server: dict[str, int]) -> None:
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{server['http']}", timeout=10
    ) as client:
        started = time.monotonic()
        resp = await client.get("/send", params={"group": "nobody", "action": "x"})
        elapsed = time.monotonic() - started
    assert resp.status_code == 200
    assert "no webclient" in resp.json()["error"]
    assert elapsed < 5  # 立即返回，不挂起


async def test_missing_params_return_error(server: dict[str, int]) -> None:
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{server['http']}", timeout=10
    ) as client:
        for params, expected in (
            ({"action": "clientTime"}, "need group"),
            ({"group": GROUP}, "need action"),
        ):
            resp = await client.get("/send", params=params)
            assert resp.status_code == 200
            assert resp.json().get("error") == expected
