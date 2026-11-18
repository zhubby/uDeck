"""
[INPUT]: 依赖共享守护进程与隔离的网络发现和 D-Bus。
[OUTPUT]: 验证关闭时零网络查询、启用后撤销检查和按需读取。
[POS]: 共享后台负载回归；不启动真实网络监听或 Samba。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from dbus_next import Message

from udeck.network_files import daemon as web
from udeck.smb_files import daemon as smb


@pytest.mark.parametrize('protocol', ['web', 'smb'])
def test_stopped_daemon_skips_network_discovery_and_owner_checks(monkeypatch, protocol):
    module = web if protocol == 'web' else smb
    calls = []

    async def discover(bus):
        calls.append('discover')
        return []

    async def tick(**kwargs):
        calls.append('tick')

    monkeypatch.setattr(module, 'discover', discover)
    manager = SimpleNamespace(value={'enabled':False}, deadline=None, tick=tick)
    args = (manager, None, None) if protocol == 'web' else (manager, None)
    asyncio.run(module._poll(*args))
    assert calls == []


@pytest.mark.parametrize('protocol', ['web', 'smb'])
def test_enabled_daemon_keeps_fresh_network_and_owner_revocation_checks(monkeypatch, protocol):
    module = web if protocol == 'web' else smb
    calls = []
    candidates = [{'key':'selected', 'addresses':['192.0.2.8']}]

    async def discover(bus):
        calls.append('discover')
        return candidates

    async def tick(**kwargs):
        calls.append(kwargs)

    async def missing_owner(*args):
        calls.append('owner')
        return False

    async def call(message):
        assert message.member == 'NameHasOwner' and message.body == ['session-owner']
        calls.append('owner')
        return SimpleNamespace(error_name=None, body=[False])

    monkeypatch.setattr(module, 'discover', discover)
    if protocol == 'smb':
        monkeypatch.setattr(smb, 'owner_alive', missing_owner)
    manager = SimpleNamespace(value={'enabled':True}, deadline=123, owner='session-owner', tick=tick)
    args = (manager, None, SimpleNamespace(call=call)) if protocol == 'web' else (manager, None)
    asyncio.run(module._poll(*args))
    assert calls == ['discover', 'owner', {'candidates':candidates, 'owner_alive':False}]


def test_stopped_web_status_reads_current_networks_on_demand(monkeypatch):
    async def scenario():
        candidates = [{'key':'current-network'}]

        async def discover(bus):
            return candidates

        manager = SimpleNamespace(value={'enabled':False}, candidates=[])
        manager.status = lambda: {'enabled':False, 'candidates':manager.candidates}
        monkeypatch.setattr(web, 'discover', discover)
        service = web.Control(manager, None)
        result = await web.Control.Status.__wrapped__(service)
        assert json.loads(result)['candidates'] == candidates
    asyncio.run(scenario())


def test_stopped_smb_status_authenticates_and_reads_current_networks(monkeypatch):
    async def scenario():
        calls, replies = [], []
        candidates = [{'key':'current-network'}]

        async def credentials(bus, sender):
            calls.append(('credentials', sender))
            return object()

        async def discover(bus):
            calls.append('discover')
            return candidates

        async def send(message):
            replies.append(json.loads(message.body[0]))

        manager = SimpleNamespace(value={'enabled':False}, candidates=[])
        manager.status = lambda: {'enabled':False, 'candidates':manager.candidates}
        monkeypatch.setattr(smb, 'credentials', credentials)
        monkeypatch.setattr(smb, 'discover', discover)
        dispatcher = smb.Dispatcher(SimpleNamespace(send=send), manager)
        message = Message(path=smb.OBJECT_PATH, interface=smb.SERVICE, member='Status', sender=':1.123', serial=1)
        await dispatcher.dispatch(message)
        assert calls == [('credentials', ':1.123'), 'discover']
        assert replies == [{'enabled':False, 'candidates':candidates}]
    asyncio.run(scenario())
