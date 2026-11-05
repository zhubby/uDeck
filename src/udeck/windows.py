import ctypes
import sys

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal

APP_ID = "io.github.zhubby.uDeck"


class Interface(ctypes.Structure):
    pass


InterfacePointer = ctypes.POINTER(Interface)


class Message(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("signature", ctypes.c_char_p),
                ("types", ctypes.POINTER(InterfacePointer))]


Interface._fields_ = [
    ("name", ctypes.c_char_p), ("version", ctypes.c_int),
    ("method_count", ctypes.c_int), ("methods", ctypes.POINTER(Message)),
    ("event_count", ctypes.c_int), ("events", ctypes.POINTER(Message)),
]


class Array(ctypes.Structure):
    _fields_ = [("size", ctypes.c_size_t), ("alloc", ctypes.c_size_t), ("data", ctypes.c_void_p)]


class WindowService(QObject):
    changed = Signal(list)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.display = None
        self.seat = None
        self.manager = None
        self.notifier = None
        self.handles = {}
        self.retained = []
        self.listeners = {}
        self.globals = {}
        self.available = False

    def start(self):
        if sys.platform != "linux":
            return
        try:
            self.library = ctypes.CDLL("libwayland-client.so.0")
            signatures = {
                "wl_display_connect": ([ctypes.c_char_p], ctypes.c_void_p),
                "wl_display_disconnect": ([ctypes.c_void_p], None),
                "wl_display_roundtrip": ([ctypes.c_void_p], ctypes.c_int),
                "wl_display_dispatch": ([ctypes.c_void_p], ctypes.c_int),
                "wl_display_flush": ([ctypes.c_void_p], ctypes.c_int),
                "wl_display_get_fd": ([ctypes.c_void_p], ctypes.c_int),
                "wl_proxy_get_id": ([ctypes.c_void_p], ctypes.c_uint32),
                "wl_proxy_get_version": ([ctypes.c_void_p], ctypes.c_uint32),
                "wl_proxy_destroy": ([ctypes.c_void_p], None),
                "wl_proxy_add_listener": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p], ctypes.c_int),
                "wl_proxy_marshal_flags": ([ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32], ctypes.c_void_p),
            }
            for name, (arguments, result) in signatures.items():
                function = getattr(self.library, name)
                function.argtypes = arguments
                function.restype = result
            self._interfaces()
            self.display = self.library.wl_display_connect(None)
            if not self.display:
                raise RuntimeError("无法连接 Wayland 会话")
            self.registry = self.library.wl_proxy_marshal_flags(self.display, 1, ctypes.byref(self.registry_interface), 1, 0, ctypes.c_void_p())
            self._listen(self.registry, [
                ((ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32), self._global),
                ((ctypes.c_uint32,), self._global_removed),
            ])
            for _iteration in range(2):
                if self.library.wl_display_roundtrip(self.display) < 0:
                    raise RuntimeError("Wayland 协议握手失败")
            self.available = bool(self.manager and self.seat)
            if not self.available:
                raise RuntimeError("当前会话未提供窗口控制协议")
            self.notifier = QSocketNotifier(self.library.wl_display_get_fd(self.display), QSocketNotifier.Type.Read, self)
            self.notifier.activated.connect(self._dispatch)
        except (OSError, RuntimeError) as error:
            self.close()
            self.failed.emit(str(error))

    def _message_array(self, entries):
        messages = (Message * len(entries))()
        for index, (name, signature, types) in enumerate(entries):
            type_array = (InterfacePointer * len(types))(*[
                ctypes.pointer(interface) if interface is not None else InterfacePointer()
                for interface in types
            ]) if types else None
            self.retained.append(type_array)
            messages[index] = Message(name.encode(), signature.encode(), type_array)
        self.retained.append(messages)
        return messages

    def _interfaces(self):
        self.registry_interface = Interface.in_dll(self.library, "wl_registry_interface")
        self.seat_interface = Interface.in_dll(self.library, "wl_seat_interface")
        self.output_interface = Interface.in_dll(self.library, "wl_output_interface")
        self.surface_interface = Interface.in_dll(self.library, "wl_surface_interface")
        self.handle_interface = Interface(b"zwlr_foreign_toplevel_handle_v1", 3, 0, None, 0, None)
        self.manager_interface = Interface(b"zwlr_foreign_toplevel_manager_v1", 3, 0, None, 0, None)
        methods = self._message_array([
            ("set_maximized", "", []), ("unset_maximized", "", []),
            ("set_minimized", "", []), ("unset_minimized", "", []),
            ("activate", "o", [self.seat_interface]), ("close", "", []),
            ("set_rectangle", "oiiii", [self.surface_interface, None, None, None, None]),
            ("destroy", "", []), ("set_fullscreen", "2?o", [self.output_interface]),
            ("unset_fullscreen", "2", []),
        ])
        events = self._message_array([
            ("title", "s", [None]), ("app_id", "s", [None]),
            ("output_enter", "o", [self.output_interface]),
            ("output_leave", "o", [self.output_interface]),
            ("state", "a", [None]), ("done", "", []), ("closed", "", []),
            ("parent", "3?o", [self.handle_interface]),
        ])
        self.handle_interface.method_count, self.handle_interface.methods = len(methods), methods
        self.handle_interface.event_count, self.handle_interface.events = len(events), events
        methods = self._message_array([("stop", "", [])])
        events = self._message_array([("toplevel", "n", [self.handle_interface]), ("finished", "", [])])
        self.manager_interface.method_count, self.manager_interface.methods = len(methods), methods
        self.manager_interface.event_count, self.manager_interface.events = len(events), events

    def _listen(self, proxy, callbacks):
        listeners = []
        retained = []
        for argument_types, function in callbacks:
            callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, *argument_types)
            callback = callback_type(lambda user_data, target, *values, handler=function: handler(target, *values))
            retained.append(callback)
            listeners.append(ctypes.cast(callback, ctypes.c_void_p).value)
        listener_array = (ctypes.c_void_p * len(listeners))(*listeners)
        self.listeners[proxy] = [listener_array, *retained]
        self.library.wl_proxy_add_listener(proxy, listener_array, None)

    def _retire_listener(self, proxy):
        QTimer.singleShot(0, lambda: self.listeners.pop(proxy, None))

    def _bind(self, name, interface, version):
        version = min(version, interface.version)
        return self.library.wl_proxy_marshal_flags(
            self.registry, 0, ctypes.byref(interface), version, 0,
            ctypes.c_uint32(name), ctypes.c_char_p(interface.name), ctypes.c_uint32(version), ctypes.c_void_p(),
        )

    def _global(self, registry, name, interface, version):
        self.globals[interface.decode()] = version
        if interface == b"zwlr_foreign_toplevel_manager_v1":
            self.manager_name = name
            self.manager = self._bind(name, self.manager_interface, version)
            self._listen(self.manager, [((ctypes.c_void_p,), self._new_handle), ((), self._finished)])
        elif interface == b"wl_seat" and not self.seat:
            self.seat = self._bind(name, self.seat_interface, min(version, 2))
            self._listen(self.seat, [((ctypes.c_uint32,), lambda *values: None),
                                     ((ctypes.c_char_p,), lambda *values: None)])

    def _global_removed(self, registry, name):
        if name == getattr(self, "manager_name", None):
            self.available = False

    def _new_handle(self, manager, handle):
        identifier = str(self.library.wl_proxy_get_id(handle))
        self.handles[identifier] = {"id": identifier, "proxy": handle, "name": "应用窗口", "appId": "", "active": False, "fullscreen": False, "parent": False}

        def update_field(proxy, value, field):
            if identifier in self.handles:
                self.handles[identifier][field] = value.decode(errors="replace")

        def update_state(proxy, value):
            if identifier not in self.handles:
                return
            values = ctypes.cast(value.contents.data, ctypes.POINTER(ctypes.c_uint32))
            states = {values[index] for index in range(value.contents.size // 4)}
            self.handles[identifier]["active"] = 2 in states
            self.handles[identifier]["maximized"] = 0 in states
            self.handles[identifier]["minimized"] = 1 in states
            self.handles[identifier]["fullscreen"] = 3 in states

        def update_parent(proxy, parent):
            if identifier in self.handles:
                self.handles[identifier]["parent"] = bool(parent)

        def closed(proxy):
            self.handles.pop(identifier, None)
            self.library.wl_proxy_marshal_flags(proxy, 7, None, self.library.wl_proxy_get_version(proxy), 1)
            self._retire_listener(proxy)
            self._emit()

        self._listen(handle, [
            ((ctypes.c_char_p,), lambda proxy, value: update_field(proxy, value, "name")),
            ((ctypes.c_char_p,), lambda proxy, value: update_field(proxy, value, "appId")),
            ((ctypes.c_void_p,), lambda *values: None), ((ctypes.c_void_p,), lambda *values: None),
            ((ctypes.POINTER(Array),), update_state), ((), lambda proxy: self._emit()),
            ((), closed), ((ctypes.c_void_p,), update_parent),
        ])

    def _emit(self):
        self.changed.emit(self.entries())

    def entries(self):
        return [{key: value for key, value in window.items() if key != "proxy"} | {
            "subtitle": window["appId"] or "应用窗口", "icon": window["appId"] or "application-x-executable",
        } for window in self.handles.values() if window["appId"] != APP_ID]

    def _finished(self, manager):
        self.available = False
        self.library.wl_proxy_destroy(manager)
        self._retire_listener(manager)
        self.manager = None

    def _dispatch(self, *arguments):
        if self.display and self.library.wl_display_dispatch(self.display) < 0:
            self.close()
            self.failed.emit("与窗口管理器的连接已断开")

    def request(self, identifier, operation):
        window = self.handles.get(str(identifier))
        if not window or not self.available:
            raise RuntimeError("窗口已关闭或窗口协议不可用")
        proxy = window["proxy"]
        opcode = {"activate": 4, "close": 5, "maximize": 0}[operation]
        arguments = [ctypes.c_void_p(self.seat)] if operation == "activate" else []
        self.library.wl_proxy_marshal_flags(proxy, opcode, None, self.library.wl_proxy_get_version(proxy), 0, *arguments)
        self.library.wl_display_flush(self.display)

    def activate_shell(self):
        for identifier, window in self.handles.items():
            if window["appId"] == APP_ID:
                self.request(identifier, "activate")
                return

    def close(self):
        if self.notifier:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None
        if self.display:
            self.library.wl_display_disconnect(self.display)
            self.display = None
        self.handles.clear()
        self.listeners.clear()
        self.available = False
