import ctypes
import os
import time

from .i18n import error_text, tr
from .windows import Interface, WindowService


class VirtualInput(WindowService):
    def __init__(self):
        super().__init__()
        self.keyboard = None
        self.pointer = None
        self.keyboard_manager = None
        self.pointer_manager = None
        self.keys = set()
        self.buttons = set()
        self.position = (640, 360)
        self.extent = (1280, 720)
        self.error = ''
        self.modifier_masks = {42: 1, 54: 1, 29: 4, 97: 4, 56: 8, 100: 8}

    def _interfaces(self):
        super()._interfaces()
        self.keyboard_interface = Interface(b'zwp_virtual_keyboard_v1', 1, 0, None, 0, None)
        self.keyboard_manager_interface = Interface(b'zwp_virtual_keyboard_manager_v1', 1, 0, None, 0, None)
        self.pointer_interface = Interface(b'zwlr_virtual_pointer_v1', 1, 0, None, 0, None)
        self.pointer_manager_interface = Interface(b'zwlr_virtual_pointer_manager_v1', 1, 0, None, 0, None)
        definitions = [
            (self.keyboard_interface, [('keymap', 'uhu', []), ('key', 'uuu', []), ('modifiers', 'uuuu', []), ('destroy', '', [])]),
            (self.keyboard_manager_interface, [('create_virtual_keyboard', 'on', [self.seat_interface, self.keyboard_interface])]),
            (self.pointer_interface, [('motion', 'uff', []), ('motion_absolute', 'uuuuu', []), ('button', 'uuu', []),
                                      ('axis', 'uuf', []), ('frame', '', []), ('axis_source', 'u', []),
                                      ('axis_stop', 'uu', []), ('axis_discrete', 'uufi', []), ('destroy', '', [])]),
            (self.pointer_manager_interface, [('create_virtual_pointer', '?on', [self.seat_interface, self.pointer_interface]), ('destroy', '', [])]),
        ]
        for interface, methods in definitions:
            interface.method_count = len(methods)
            interface.methods = self._message_array(methods)

    def _global(self, registry, name, interface, version):
        super()._global(registry, name, interface, version)
        if interface == b'zwp_virtual_keyboard_manager_v1':
            self.keyboard_manager = self._bind(name, self.keyboard_manager_interface, 1)
        elif interface == b'zwlr_virtual_pointer_manager_v1':
            self.pointer_manager = self._bind(name, self.pointer_manager_interface, 1)

    def start(self):
        super().start()
        if not self.display:
            self.error = tr('无法连接 Wayland 虚拟输入')
            return
        try:
            if not self.keyboard_manager or not self.pointer_manager or not self.seat:
                raise RuntimeError(tr('合成器未提供虚拟键盘或虚拟指针协议'))
            self.keyboard = self.library.wl_proxy_marshal_flags(self.keyboard_manager, 0, ctypes.byref(self.keyboard_interface), 1, 0,
                                                               ctypes.c_void_p(self.seat), ctypes.c_void_p())
            self.pointer = self.library.wl_proxy_marshal_flags(self.pointer_manager, 0, ctypes.byref(self.pointer_interface), 1, 0,
                                                              ctypes.c_void_p(self.seat), ctypes.c_void_p())
            self._keymap()
            self._flush()
            self.available = True
        except (OSError, RuntimeError) as error:
            self.error = error_text(error)
            self.close()

    def _request(self, proxy, opcode, *arguments):
        self.library.wl_proxy_marshal_flags(proxy, opcode, None, 1, 0, *arguments)

    def _flush(self):
        if self.display:
            self.library.wl_display_flush(self.display)

    def _keymap(self):
        library = ctypes.CDLL('libxkbcommon.so.0')
        definitions = {'xkb_context_new': ([ctypes.c_int], ctypes.c_void_p),
                       'xkb_keymap_new_from_string': ([ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int], ctypes.c_void_p),
                       'xkb_keymap_get_as_string': ([ctypes.c_void_p, ctypes.c_int], ctypes.c_void_p),
                       'xkb_keymap_mod_get_index': ([ctypes.c_void_p, ctypes.c_char_p], ctypes.c_uint),
                       'xkb_keymap_unref': ([ctypes.c_void_p], None), 'xkb_context_unref': ([ctypes.c_void_p], None)}
        for name, (arguments, result) in definitions.items():
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result
        context = library.xkb_context_new(0)
        definition = (b'xkb_keymap { xkb_keycodes { include "evdev+aliases(qwerty)" }; '
                      b'xkb_types { include "complete" }; xkb_compat { include "complete" }; '
                      b'xkb_symbols { include "pc+us+inet(evdev)" key <FK24> { [ F24 ] }; }; };')
        keymap = library.xkb_keymap_new_from_string(context, definition, 1, 0) if context else None
        allocation = None
        try:
            if not keymap:
                raise RuntimeError(tr('无法创建虚拟键盘映射'))
            allocation = library.xkb_keymap_get_as_string(keymap, 1)
            if not allocation:
                raise RuntimeError(tr('无法序列化虚拟键盘映射'))
            contents = ctypes.string_at(allocation) + b'\0'
            for codes, name in [((42, 54), b'Shift'), ((29, 97), b'Control'), ((56, 100), b'Mod1')]:
                index = library.xkb_keymap_mod_get_index(keymap, name)
                for code in codes:
                    self.modifier_masks[code] = 1 << index if index < 32 else 0
            descriptor = os.memfd_create('udeck-keymap', os.MFD_CLOEXEC)
            try:
                os.write(descriptor, contents)
                self._request(self.keyboard, 0, ctypes.c_uint32(1), ctypes.c_int32(descriptor), ctypes.c_uint32(len(contents)))
                self._flush()
            finally:
                os.close(descriptor)
        finally:
            if allocation:
                libc = ctypes.CDLL(None)
                libc.free.argtypes = [ctypes.c_void_p]
                libc.free(allocation)
            if keymap:
                library.xkb_keymap_unref(keymap)
            if context:
                library.xkb_context_unref(context)

    def _timestamp(self):
        return ctypes.c_uint32(int(time.monotonic() * 1000) & 0xffffffff)

    def _key(self, code, pressed):
        if pressed:
            self.keys.add(code)
        else:
            self.keys.discard(code)
        self._request(self.keyboard, 1, self._timestamp(), ctypes.c_uint32(code), ctypes.c_uint32(pressed))
        modifiers = 0
        for held in self.keys:
            modifiers |= self.modifier_masks.get(held, 0)
        self._request(self.keyboard, 2, ctypes.c_uint32(modifiers), ctypes.c_uint32(0), ctypes.c_uint32(0), ctypes.c_uint32(0))
        self._flush()

    def chord(self, codes):
        if not self.available:
            return
        try:
            for code in codes:
                self._key(code, True)
        finally:
            for code in reversed(codes):
                self._key(code, False)

    def button(self, code, pressed):
        if not self.available or (code in self.buttons) == pressed:
            return
        if pressed:
            self.buttons.add(code)
        else:
            self.buttons.discard(code)
        self._request(self.pointer, 2, self._timestamp(), ctypes.c_uint32(code), ctypes.c_uint32(pressed))
        self._request(self.pointer, 4)
        self._flush()

    def move(self, horizontal, vertical):
        if not self.available:
            return
        width, height = self.extent
        self.position = (max(0, min(width - 1, self.position[0] + horizontal)),
                         max(0, min(height - 1, self.position[1] + vertical)))
        self._request(self.pointer, 1, self._timestamp(), ctypes.c_uint32(int(self.position[0])), ctypes.c_uint32(int(self.position[1])),
                      ctypes.c_uint32(width), ctypes.c_uint32(height))
        self._request(self.pointer, 4)
        self._flush()

    def scroll(self, amount):
        if self.available:
            self._request(self.pointer, 5, ctypes.c_uint32(0))
            self._request(self.pointer, 7, self._timestamp(), ctypes.c_uint32(0), ctypes.c_int32(amount * 15 * 256), ctypes.c_int32(amount))
            self._request(self.pointer, 4)
            self._flush()

    def release_all(self):
        if self.available:
            for code in list(self.keys):
                self._key(code, False)
            for code in list(self.buttons):
                self.button(code, False)
        self.keys.clear()
        self.buttons.clear()

    def close(self):
        self.release_all()
        if self.display:
            for proxy, opcode in ((self.keyboard, 3), (self.pointer, 8), (self.pointer_manager, 1)):
                if proxy:
                    self.library.wl_proxy_marshal_flags(proxy, opcode, None, 1, 1)
            self._flush()
        self.keyboard = self.pointer = self.pointer_manager = self.keyboard_manager = None
        super().close()
