from PySide6.QtCore import QCoreApplication

from udeck.directions import DirectionReader


def test_direction_reader_ignores_modified_arrows_and_waits_for_release():
    application = QCoreApplication.instance() or QCoreApplication([])
    reader = DirectionReader()
    events = []
    reader.direction.connect(lambda action, pressed: events.append((action, pressed)))
    reader.feed(106, 1)
    reader.feed(29, 1)
    reader.feed(106, 2)
    reader.feed(29, 0)
    reader.feed(106, 2)
    reader.feed(106, 0)
    reader.feed(106, 1)
    assert events == [('right', True), ('right', False), ('right', False), ('right', True)]
    reader.close()
    assert application


def test_direction_reader_does_not_treat_letters_as_buttons():
    application = QCoreApplication.instance() or QCoreApplication([])
    reader = DirectionReader()
    events = []
    reader.direction.connect(lambda *arguments: events.append(arguments))
    for code in (30, 36, 37, 23):
        reader.feed(code, 1)
    assert not events
    reader.close()
    assert application
