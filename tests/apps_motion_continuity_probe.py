"""
[INPUT]: 依赖真实 Qt 视图、隔离控制器与延迟图像服务。
[OUTPUT]: 验证切页改向、封面身份与编码 URL、标题重选。
[POS]: 共享应用动效的独立进程探针；不连接设备。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from udeck import main
from udeck.apps.common.controller import AppController


def wait(predicate, seconds=4):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(5)
    assert predicate()


def visual(owner, name):
    queue = [owner.contentItem() if hasattr(owner, 'contentItem') else owner]
    while queue:
        item = queue.pop()
        if item.objectName() == name:
            return item
        queue.extend(item.childItems())
    raise AssertionError(('missing visual', name))


class Controller(AppController):
    def create_library(self, app):
        return None

    def tabs(self):
        return ['One', 'Two', 'Three']

    def rows(self):
        return [{'id': str(index), 'title': 'Track ' + str(index), 'subtitle': 'Fixture'}
                for index in range(48)]


def run():
    root, mode, theme = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    root.mkdir(parents=True, exist_ok=True)
    reduced = os.environ.get('UDECK_REDUCED_MOTION') == '1'
    application = QApplication([])
    controller = Controller('music', root / 'state', root / 'settings.json')
    controller.theme = theme
    controller.poller.stop()
    engine = QQmlApplicationEngine()
    errors = []
    engine.warnings.connect(lambda warnings: errors.extend(w.toString() for w in warnings))
    engine.addImageProvider('desktop', main.IconProvider())
    engine.rootContext().setContextProperty('controller', controller)
    engine.rootContext().setContextProperty('windowed', True)
    qml = Path(main.__file__).parent / 'apps/common/qml'
    window = None
    server = None
    try:
        if mode == 'pages':
            engine.load(QUrl.fromLocalFile(str(qml / 'Main.qml')))
            assert engine.rootObjects(), errors
            window = engine.rootObjects()[0]
            QTest.qWait(180)
            page = visual(window, 'appPageContent')
            controller.setTab(1)
            application.processEvents()
            assert page.opacity() == 1, 'A tab change must never clear the page'
            QTest.qWait(25)
            before = page.property('offsetX')
            controller.setTab(2)
            controller.setTab(0)
            application.processEvents()
            assert page.opacity() == 1
            if not reduced:
                assert abs(page.property('offsetX')) <= abs(before) + 0.2, 'Rapid navigation reset the visual offset'
            QTest.qWait(160)
            assert abs(page.property('offsetX')) < 0.1
            controller.folder = 'Changed folder'
            controller.publish()
            application.processEvents()
            assert page.opacity() == 1 and abs(page.property('offsetX')) < 0.1, 'A folder update replayed the entire page'
            controller.notice = 'Scan complete'
            controller.publish()
            application.processEvents()
            assert page.opacity() == 1 and abs(page.property('offsetX')) < 0.1
            cards = visual(window, 'appCards')
            controller.select('9')
            application.processEvents()
            wait(lambda: cards.property('currentItem') is not None)
            QTest.qWait(130)
            selected = cards.property('currentItem')
            assert selected.y() >= cards.property('contentY') - 1
            assert selected.y() + selected.height() <= cards.property('contentY') + cards.height() + 1
            controller.select('15')
            application.processEvents()
            controller.select('0')
            application.processEvents()
            assert controller.selectedIndex == 0
            QTest.qWait(130)
            assert cards.property('contentY') < 1, 'An interrupted viewport moved toward an old selection'
            controller.menu('Small', [('One', lambda: None), ('Two', lambda: None)])
            QTest.qWait(180)
            panel = visual(window, 'appMenuPanel')
            shade = visual(window, 'applicationModal')
            initial = panel.height()
            controller.menu('Larger', [(str(index), lambda: None) for index in range(6)])
            application.processEvents()
            if not reduced:
                assert abs(panel.height() - initial) < 1, 'Menu replacement jumped to its final height'
            assert shade.opacity() == 1, 'Menu replacement replayed the shade'
            QTest.qWait(160)
            assert panel.height() > initial + 20
            controller.dispatch('back')
            controller.menu('Latest', [('New', lambda: None)])
            QTest.qWait(180)
            assert shade.isVisible() and visual(window, 'appMenuTitle').property('text') == 'Latest', 'Old closing work cleared a new menu'
        else:
            window = QQuickWindow()
            window.setWidth(420)
            window.setHeight(260)
            window.show()
            component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml / ('Artwork.qml' if mode == 'artwork' else 'ScrollingTitle.qml'))))
            properties = {'fontFamily': 'DejaVu Sans', 'width': 180, 'height': 120,
                          'reducedMotion': reduced}
            if mode == 'artwork':
                palette_component = QQmlComponent(engine, QUrl.fromLocalFile(str(Path(main.__file__).parent / 'qml/ThemePalette.qml')))
                palette = palette_component.createWithInitialProperties({'theme': theme})
                palette.setParent(engine)
                properties.update(colors=palette, kind='emulator', identity='A')
            else:
                properties.update(text='A long selected game title', selected=True, active=True, resetKey='A')
            item = component.createWithInitialProperties(properties)
            assert item is not None, [error.toString() for error in component.errors()]
            item.setParent(window.contentItem())
            item.setParentItem(window.contentItem())
            if mode == 'artwork':
                images = {}
                for name, color in (('red', 0xFFFF0000), ('blue', 0xFF0000FF)):
                    image = QImage(24, 24, QImage.Format.Format_ARGB32)
                    image.fill(color)
                    buffer = QBuffer()
                    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                    assert image.save(buffer, 'PNG')
                    images[name] = bytes(buffer.data())

                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        if 'slow' in self.path:
                            time.sleep(0.22)
                        name = 'blue' if 'blue' in self.path else 'red'
                        self.send_response(404 if 'missing' in self.path else 200)
                        self.end_headers()
                        try:
                            self.wfile.write(images[name])
                        except BrokenPipeError:
                            pass

                    def log_message(self, *args):
                        pass

                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                base = f'http://127.0.0.1:{server.server_port}'
                red, blue = base + '/red.png', base + '/slow-blue.png'
                item.setProperty('cover', red)
                wait(lambda: item.property('displayedSource') == red)
                QTest.qWait(140)
                item.setProperty('cover', blue)
                application.processEvents()
                assert item.property('displayedSource') == red, 'The same item lost its old cover while loading'
                wait(lambda: item.property('displayedSource') == blue)
                if not reduced:
                    QTest.qWait(35)
                    assert 0 < item.property('blend') < 1
                    color = window.grabWindow().pixelColor(80, 60)
                    assert color.red() + color.blue() >= 245 and color.green() < 5, 'The cover crossfade mixed in its background'
                item.setProperty('identity', 'B')
                item.setProperty('cover', base + '/slow-red.png')
                application.processEvents()
                assert item.property('displayedIdentity') != 'A', 'An old cover was paired with a new item'
                item.setProperty('identity', 'A')
                item.setProperty('cover', red)
                wait(lambda: item.property('displayedSource') == red)
                QTest.qWait(300)
                assert item.property('displayedSource') == red, 'A late image replaced the latest selection'
                item.setProperty('cover', base + '/missing.png')
                QTest.qWait(280)
                assert item.property('displayedSource') == red, 'A failed same-item replacement removed a valid cover'
                item.setProperty('identity', 'Missing')
                application.processEvents()
                assert not item.property('displayedSource'), 'A failed new identity retained another item cover'
                item.setProperty('cover', base + '/slow-blue-cancelled.png')
                application.processEvents()
                item.setProperty('cover', '')
                QTest.qWait(300)
                assert not item.property('displayedSource'), 'A cancelled image request was displayed later'
                local_cover = root / '本地 cover with spaces.png'
                local_cover.write_bytes(images['red'])
                item.setProperty('identity', 'encoded-local')
                item.setProperty('cover', local_cover.as_uri())
                wait(lambda: item.property('displayedSource') == QUrl.fromLocalFile(str(local_cover)).toString())
            else:
                label = visual(item, 'cardTitleText')
                item.setWidth(label.implicitWidth() - 18)
                QTest.qWait(1000)
                assert item.property('offset') == 0
                if reduced:
                    QTest.qWait(700)
                    assert item.property('offset') == 0 and not item.property('animating')
                else:
                    wait(lambda: item.property('offset') > 1)
                    wait(lambda: not item.property('animating'), 4)
                    assert abs(item.property('offset')) < 0.1
                    QTest.qWait(1500)
                    assert item.property('offset') == 0 and not item.property('animating'), 'A title scrolled repeatedly while idle'
                    item.setProperty('active', False)
                    item.setProperty('active', True)
                    QTest.qWait(1400)
                    assert item.property('completed') and not item.property('animating'), 'Foreground/menu restoration replayed a completed title'
                    item.setProperty('visible', False)
                    item.setProperty('visible', True)
                    QTest.qWait(1400)
                    assert item.property('completed') and not item.property('animating'), 'Visibility restoration replayed a completed title'
                    item.setProperty('selected', False)
                    item.setProperty('selected', True)
                    wait(lambda: item.property('offset') > 1)
                    item.setProperty('reducedMotion', True)
                    application.processEvents()
                    assert item.property('offset') == 0 and not item.property('animating')
        assert not [error for error in errors if '/missing.png' not in error], errors
        print(json.dumps({'passed': True, 'mode': mode, 'reduced': reduced, 'theme': theme}), flush=True)
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if window:
            window.hide()
            if mode != 'pages':
                delete(window)
        delete(engine)
        controller.close()


if __name__ == '__main__':
    run()
