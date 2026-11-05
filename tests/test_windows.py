from types import SimpleNamespace

from udeck.windows import WindowService


def test_wayland_callbacks_are_owned_by_proxy_and_released_on_close():
    windows = WindowService()
    windows.library = SimpleNamespace(wl_proxy_add_listener=lambda *arguments: 0)
    windows._listen(123, [((), lambda proxy: None)])
    assert 123 in windows.listeners
    assert windows.retained == []
    windows.close()
    assert windows.listeners == {}
