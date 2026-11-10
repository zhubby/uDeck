"""Forward launch requests without importing Qt or starting a graphical process."""

import asyncio
import os

from .app_routing import object_path, service_name


async def _forward(app_id, payload, doctor):
    from dbus_next import Message, MessageType
    from dbus_next.aio import MessageBus

    bus = MessageBus()
    try:
        await bus.connect()
        owner = await bus.call(Message(destination='org.freedesktop.DBus', path='/org/freedesktop/DBus',
                                       interface='org.freedesktop.DBus', member='NameHasOwner',
                                       signature='s', body=[service_name(app_id)]))
        if owner.message_type == MessageType.ERROR:
            raise RuntimeError(owner.body[0] if owner.body else owner.error_name)
        if not owner.body or not owner.body[0]:
            return None
        while True:
            reply = await bus.call(Message(destination=service_name(app_id), path=object_path(app_id),
                                           interface=app_id + '.Control', member='Diagnose' if doctor else 'Open',
                                           signature='' if doctor else 's', body=[] if doctor else [payload]))
            if reply.message_type != MessageType.ERROR:
                break
            if reply.error_name in ('org.freedesktop.DBus.Error.ServiceUnknown',
                                    'org.freedesktop.DBus.Error.NameHasNoOwner'):
                return None
            if reply.error_name in ('org.freedesktop.DBus.Error.UnknownObject',
                                    'org.freedesktop.DBus.Error.UnknownInterface',
                                    'org.freedesktop.DBus.Error.UnknownMethod'):
                # A cold launcher reserves its name before it creates the Qt object.
                # The outer timeout bounds this wait without starting a duplicate.
                await asyncio.sleep(.02)
                continue
            raise RuntimeError(reply.body[0] if reply.body else reply.error_name)
        if reply.signature != 's' or len(reply.body) != 1:
            raise RuntimeError('Invalid application response')
        if not doctor and reply.body[0]:
            raise RuntimeError(reply.body[0])
        return reply.body[0]
    finally:
        bus.disconnect()


def forward_existing(app_id, payload='', *, doctor=False):
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        return None
    try:
        return asyncio.run(asyncio.wait_for(_forward(app_id, payload, doctor), timeout=2))
    except TimeoutError as error:
        raise RuntimeError('The running application did not respond') from error
    except (OSError, EOFError) as error:
        raise RuntimeError(f'Cannot reach the application session: {error}') from error
