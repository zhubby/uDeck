"""Forward terminal requests before loading the graphical runtime."""

import json
import sys

from ..core import ConfigStore
from ..i18n import render
from ..ipc_client import forward_existing
from ..performance import StartupTrace
from . import APP_ID
from .core import parse_launch, plugin_paths


def main(argv=None):
    trace = StartupTrace()
    try:
        request, options = parse_launch(argv)
        request.executable()
        if not options.mock:
            reply = forward_existing(APP_ID, request.to_json(), doctor=options.doctor)
            if reply is not None:
                if options.doctor:
                    print(reply)
                return 0
            if options.doctor:
                print(json.dumps({'running': False, 'plugins': [str(p) for p in plugin_paths()]}, ensure_ascii=False))
                return 0
        from .runtime import main as run

        return run(request=request, options=options, trace=trace)
    except (ValueError, RuntimeError) as error:
        print(render(error, ConfigStore().data['preferences']['language']), file=sys.stderr)
        return 2


def __getattr__(name):
    if name == 'Coordinator':
        from . import runtime

        return getattr(runtime, name)
    raise AttributeError(name)


if __name__ == '__main__':
    raise SystemExit(main())
