from pathlib import Path

from openhasp_config_manager.gui.domain.variables.usage_preview import group_by_file, preview_of
from openhasp_config_manager.gui.domain.variables.usages import Usage
from tests import TestBase


def _usage(path: str, line: int, column: int = 0, length: int = 1) -> Usage:
    return Usage(Path(path), line, column, length)


class TestGroupByFile(TestBase):
    def test_usages_are_grouped_in_the_order_of_their_first_usage(self):
        usages = [_usage("b", 1), _usage("a", 2), _usage("b", 3)]
        assert group_by_file(usages) == {Path("b"): [usages[0], usages[2]], Path("a"): [usages[1]]}


class TestPreviewOf(TestBase):
    LINES = ["zero", "    one", "    two {{ x }}", "      three", "four", "five"]

    def test_shows_the_lines_around_the_usage(self):
        preview = preview_of(_usage("f", 3, 8, 7), self.LINES, context=2)
        assert preview.first_line == 1
        assert preview.lines == self.LINES[:5]
        assert preview.index == 2
        assert (preview.column, preview.length) == (8, 7)

    def test_the_indentation_all_lines_share_is_removed(self):
        preview = preview_of(_usage("f", 3, 8, 7), self.LINES, context=1)
        assert preview.first_line == 2
        assert preview.lines == ["one", "two {{ x }}", "  three"]
        assert preview.column == 4

    def test_stops_at_the_start_and_the_end_of_the_file(self):
        first = preview_of(_usage("f", 1), self.LINES, context=2)
        assert (first.first_line, first.index, len(first.lines)) == (1, 0, 3)
        last = preview_of(_usage("f", 6), self.LINES, context=2)
        assert (last.first_line, last.index, len(last.lines)) == (4, 2, 3)
