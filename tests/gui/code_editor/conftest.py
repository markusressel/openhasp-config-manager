"""Fixtures of the tests of the code editor."""


import pytest

pytest.importorskip("PyQt6")


from openhasp_config_manager.gui.domain.source.syntax import Language  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor.editor import CodeEditor  # noqa: E402


@pytest.fixture
def editor(qapp, settings):
    widget = CodeEditor(Language.JSONL)
    widget.resize(500, 300)
    widget.show()
    yield widget
    widget.close()
