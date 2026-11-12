"""Keep one Qt application alive while in-process controller tests run."""

import gc
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    # Recreating QCoreApplication between fixtures leaves native objects from
    # earlier tests attached to a destroyed event dispatcher. Use QApplication
    # so the same instance also supports the tests that require GUI services.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(autouse=True)
def collect_qt_objects(qt_application):
    yield
    # Dispose cycles from closed controllers between event-loop iterations.
    # Collecting them inside a later test's processEvents can invalidate native
    # socket notifiers while the GLib dispatcher is iterating its poll list.
    from PySide6.QtCore import QCoreApplication, QEvent

    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
