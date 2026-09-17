import pytest

from tests.support.paths import EXAMPLES, ROOT

__all__ = ["EXAMPLES", "ROOT"]


@pytest.fixture
def qtbot():
    from qtpy.QtTest import QTest
    from qtpy.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    widgets = []

    class QtBot:
        @staticmethod
        def addWidget(widget) -> None:
            widgets.append(widget)

        @staticmethod
        def keyClick(widget, key, modifier=None) -> None:
            if modifier is None:
                QTest.keyClick(widget, key)
            else:
                QTest.keyClick(widget, key, modifier)
            application.processEvents()

        @staticmethod
        def keyClicks(widget, text: str) -> None:
            QTest.keyClicks(widget, text)
            application.processEvents()

        @staticmethod
        def mouseClick(widget, button) -> None:
            QTest.mouseClick(widget, button)
            application.processEvents()

    yield QtBot()

    for widget in reversed(widgets):
        widget.close()
        widget.deleteLater()
    application.processEvents()
