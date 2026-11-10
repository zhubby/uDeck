"""Lightweight entry; load the GUI only when no instance owns the session."""

import argparse
import json
import sys
from pathlib import Path

from udeck.app_routing import APP_IDS
from udeck.ipc_client import forward_existing
from udeck.performance import StartupTrace


def parse_options(argv=None):
    parser = argparse.ArgumentParser(description='uDeck native applications')
    parser.add_argument('app', choices=list(APP_IDS))
    parser.add_argument('files', nargs='*')
    parser.add_argument('--source', type=Path, action='append', default=[])
    parser.add_argument('--windowed', action='store_true')
    parser.add_argument('--no-input', action='store_true')
    parser.add_argument('--isolated', action='store_true', help='Use temporary state, without desktop IPC or hardware input')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--language', choices=('en', 'zh_CN'))
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--command', choices=('pause-game', 'now-playing', 'settings', 'sources'))
    parser.add_argument('--doctor', action='store_true')
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--quit-after', type=float, default=0)
    options = parser.parse_args(argv)
    if options.app == 'browser' and options.source:
        parser.error('--source is only available for local content apps')
    if options.smoke_test and not options.isolated:
        parser.error('--smoke-test requires --isolated')
    return options


def main(argv=None):
    trace = StartupTrace()
    options = parse_options(argv)
    if not options.isolated:
        try:
            reply = forward_existing(APP_IDS[options.app], json.dumps(
                {'files': options.files, 'command': options.command or ''}), doctor=options.doctor)
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 1
        if reply is not None:
            if options.doctor:
                print(reply)
            return 0
        if options.doctor:
            print(json.dumps({'app': options.app, 'running': False}))
            return 0
    from .runtime import main as run

    return run(options=options, trace=trace)


def __getattr__(name):
    # Keep existing Python probes compatible without importing the GUI at entry.
    if name in ('AppControl', 'make_controller'):
        from . import runtime

        return getattr(runtime, name)
    raise AttributeError(name)


def music():
    return main(['music', *sys.argv[1:]])


def video():
    return main(['video', *sys.argv[1:]])


def browser():
    return main(['browser', *sys.argv[1:]])


def reader():
    return main(['reader', *sys.argv[1:]])


def emulator():
    return main(['emulator', *sys.argv[1:]])


if __name__ == '__main__':
    raise SystemExit(main())
