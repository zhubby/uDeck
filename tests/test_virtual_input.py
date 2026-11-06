from udeck.virtual_input import VirtualInput


def test_chord_releases_modifiers_and_all_keys_even_if_transport_fails():
    output = VirtualInput()
    output.available = True
    events = []
    output._key = lambda code, pressed: events.append((code, pressed))
    output.chord((42, 68))
    assert events == [(42, True), (68, True), (68, False), (42, False)]
    assert not output.keys


def test_drag_release_is_idempotent_and_motion_clamps_to_output():
    output = VirtualInput()
    events = []
    output.available = True
    output.pointer = 20
    output._request = lambda *arguments: events.append(arguments)
    output._flush = lambda: None
    output.button(272, True)
    output.button(272, True)
    output.release_all()
    output.release_all()
    states = [arguments[-1].value for arguments in events if arguments[1] == 2]
    assert states == [1, 0]
    output.move(-10000, 10000)
    assert output.position == (0, 719)


def test_disconnected_virtual_input_does_not_queue_keys_for_next_connection():
    output = VirtualInput()
    output.chord((28,))
    output.button(272, True)
    output.move(10, 10)
    assert not output.keys and not output.buttons
