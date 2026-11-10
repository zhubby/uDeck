"""Independent dbus-next service: graphical launchers must forward without Qt GUI."""

# ruff: noqa: F821 -- D-Bus signatures use string annotations.

import asyncio
import json
import os
import sys

from dbus_next import DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method

from udeck.app_routing import object_path, service_name


async def run(app):
    app_id = 'io.github.zhubby.uDeck.' + app.title()
    requests = []
    failure = [False]

    class Control(ServiceInterface):
        @method()
        async def Open(self, payload: 's') -> 's':
            if failure[0] == 'timeout':
                await asyncio.sleep(3)
            elif failure[0]:
                raise DBusError('org.example.Refused', 'request refused')
            requests.append(json.loads(payload))
            return ''

        @method()
        def Diagnose(self) -> 's':
            return json.dumps({'app': app, 'independentService': True})

    bus = await MessageBus().connect()
    control = Control(app_id + '.Control')
    await bus.request_name(service_name(app_id))
    env = {**os.environ, 'QT_QPA_PLATFORM': 'udeck-nonexistent-platform', 'PYTHONPATH': 'src'}
    entry = [sys.executable, '-m', 'udeck.terminal.main' if app == 'terminal' else 'udeck.apps.main']
    if app != 'terminal':
        entry.append(app)

    async def invoke(arguments, expected=0):
        child = await asyncio.create_subprocess_exec(*arguments, env=env,
                                                     stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        output, errors = await asyncio.wait_for(child.communicate(), 10)
        assert child.returncode == expected, (child.returncode, output.decode(), errors.decode())
        assert b'platform plugin' not in errors
        return output.decode(), errors.decode()

    try:
        # A starting process can own its name before its Qt object is ready.
        async def export_when_ready():
            await asyncio.sleep(.15)
            bus.export(object_path(app_id), control)

        exporting = asyncio.create_task(export_when_ready())
        output, _errors = await invoke([*entry, '--doctor'])
        await exporting
        assert json.loads(output)['independentService'] is True
        if app == 'terminal':
            await invoke([*entry, '--new-window', '-T', 'Original title', '-e', '/bin/echo', 'argument with spaces'])
            assert requests[-1]['argv'] == ['/bin/echo', 'argument with spaces']
            assert requests[-1]['new_window'] is True and requests[-1]['title'] == 'Original title'
            await invoke(entry)
            assert requests[-1]['argv'] == [] and requests[-1]['new_window'] is False
        else:
            await invoke([*entry, '--command', 'settings'])
            assert requests[-1] == {'files': [], 'command': 'settings'}
        await invoke([sys.executable, 'tests/native_shell_forward_probe.py', app])
        if app != 'terminal':
            assert requests[-1] == {'files': [], 'command': ''}
        else:
            assert requests[-1]['argv'] == [] and requests[-1]['new_window'] is False
        output, _errors = await invoke([*entry, '--doctor'])
        assert json.loads(output) == {'app': app, 'independentService': True}
        before = len(requests)
        failure[0] = True
        _output, errors = await invoke(entry, expected=2 if app == 'terminal' else 1)
        assert 'request refused' in errors and len(requests) == before
        await invoke([sys.executable, 'tests/native_shell_forward_probe.py', app, 'refused'])
        failure[0] = 'timeout'
        _output, errors = await invoke(entry, expected=2 if app == 'terminal' else 1)
        assert 'did not respond' in errors and len(requests) == before
        await bus.release_name(service_name(app_id))
        output, _errors = await invoke([*entry, '--doctor'])
        assert json.loads(output)['running'] is False
        await invoke([sys.executable, 'tests/native_shell_forward_probe.py', app, 'missing'])
        print(json.dumps({'app': app, 'forwardingWithoutGui': 'passed', 'refusedRequestDidNotSpawn': True}))
    finally:
        bus.disconnect()


if __name__ == '__main__':
    asyncio.run(run(sys.argv[1]))
