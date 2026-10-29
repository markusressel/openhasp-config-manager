"""Helpers of the tests of the code editor."""


import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtTest import QTest  # noqa: E402



def _type(editor, text):
    QTest.keyClicks(editor, text)
