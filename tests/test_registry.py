# -*- coding: UTF-8 -*-
"""注册表单元测试：注册/注销/按组选取/不可用信号。"""
from jsrpc.registry import Registry


class FakeWs:
    """占位连接对象，仅用于身份比较。"""

    def __init__(self, name: str) -> None:
        self.name = name


def test_pick_returns_registered_webclient() -> None:
    reg = Registry()
    ws = FakeWs("c1")
    reg.register_webclient("g", "c1", ws)
    assert reg.pick_webclient("g") is ws


def test_pick_unknown_group_returns_none() -> None:
    reg = Registry()
    assert reg.pick_webclient("nobody") is None


def test_pick_empty_group_after_unregister_returns_none() -> None:
    reg = Registry()
    reg.register_webclient("g", "c1", FakeWs("c1"))
    reg.unregister_webclient("g", "c1")
    assert reg.pick_webclient("g") is None


def test_unregister_unknown_client_is_noop() -> None:
    reg = Registry()
    reg.unregister_webclient("g", "ghost")
    reg.unregister_webclient("unknown-group", "ghost")
    reg.unregister_apiclient("g", "ghost")


def test_pick_webclient_only_from_its_group() -> None:
    reg = Registry()
    a, b = FakeWs("a"), FakeWs("b")
    reg.register_webclient("g1", "a", a)
    reg.register_webclient("g1", "b", b)
    reg.register_webclient("g2", "other", FakeWs("other"))
    for _ in range(50):
        assert reg.pick_webclient("g1") in (a, b)


def test_stale_unregister_does_not_evict_reconnected_client() -> None:
    """client.js 固定 clientId 快速重连后，迟到的旧连接注销不得误删新注册。"""
    reg = Registry()
    old, new = FakeWs("old"), FakeWs("new")
    reg.register_webclient("g", "c1", old)
    reg.register_webclient("g", "c1", new)
    reg.unregister_webclient("g", "c1", old)
    assert reg.pick_webclient("g") is new
    reg.unregister_webclient("g", "c1", new)
    assert reg.pick_webclient("g") is None


def test_apiclient_lookup_roundtrip() -> None:
    reg = Registry()
    ws = FakeWs("api1")
    reg.register_apiclient("g", "seq-1", ws)
    assert reg.get_apiclient("g", "seq-1") is ws
    assert reg.get_apiclient("g", "seq-2") is None
    assert reg.get_apiclient("other", "seq-1") is None
    reg.unregister_apiclient("g", "seq-1")
    assert reg.get_apiclient("g", "seq-1") is None
