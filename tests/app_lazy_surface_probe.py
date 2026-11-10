"""Exercise deferred Reader surfaces with a real PDF and the real Qt Quick view."""

import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

import udeck
from udeck.apps.common.library import Source, scan
from udeck.apps.main import make_controller
from udeck.apps.reader.controller import PdfImages

os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
QtWebEngineQuick.initialize()
application = QApplication([])
with tempfile.TemporaryDirectory() as task_dir:
    root = Path(task_dir)
    content = root / 'content'
    content.mkdir()
    pdf_format = sys.argv[1] == 'pdf'
    if pdf_format:
        pdf = QPdfWriter(str(content / 'Original.pdf'))
        painter = QPainter(pdf)
        painter.drawText(100, 500, 'Original performance regression fixture')
        painter.end()
        del pdf
    else:
        (content / 'Original.txt').write_text('Original reader fixture\n\n' + '中文阅读正文。\n\n' * 100)
    controller = make_controller('reader', root / 'state', root / 'settings.json')
    controller.library.sources = [Source.create(content)]
    controller.library.items = scan(controller.library.sources[0], 'reader')
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.addImageProvider('pdf', PdfImages(controller))
    engine.rootContext().setContextProperty('controller', controller)
    engine.rootContext().setContextProperty('windowed', True)
    engine.load(QUrl.fromLocalFile(str(Path(udeck.__file__).parent / 'apps/common/qml/Main.qml')))
    assert engine.rootObjects(), errors
    window = engine.rootObjects()[0]
    controller.window = window
    loader = window.findChild(QObject, 'appSurface')
    QTest.qWait(150)
    assert loader.property('item') is None, 'Reader loaded its content surface on the bookshelf'
    identifier = controller.library.items[0]['id']
    if pdf_format:
        controller.store.data['positions'][identifier] = {'page': 0, 'y': 120, 'zoom': 1.0, 'fit': True}
    controller.open_item(identifier)
    deadline = time.monotonic() + 5
    while (loader.property('item') is None or not controller.reader_ready) and time.monotonic() < deadline:
        QTest.qWait(10)
    surface = loader.property('item')
    assert surface is not None and controller.reader_ready, errors
    QTest.qWait(150)
    if pdf_format:
        pdf_view = next(child for child in surface.findChildren(QObject)
                        if child.metaObject().indexOfProperty('contentY') >= 0)
        assert pdf_view.property('contentY') == 120, 'First lazy PDF view did not restore saved pan'
        assert controller.pdf_y == 120, f'First lazy PDF open lost saved pan: {controller.pdf_y}'
    controller.back()
    controller.publish()
    QTest.qWait(50)
    assert loader.property('item') is surface, 'Returning to the library destroyed the retained document surface'
    assert not errors, errors
    controller.close()
    window.setProperty('allowClose', True)
    window.close()
    delete(engine)
print('deferred-reader-surface-passed')
