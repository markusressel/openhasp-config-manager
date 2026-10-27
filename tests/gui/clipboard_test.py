from openhasp_config_manager.gui.domain.draft.clipboard import (
    PASTE_OFFSET,
    PasteCascade,
    objects_from_text,
    objects_to_text,
    with_descendants,
)
from tests import TestBase


class TestClipboard(TestBase):
    def test_objects_survive_the_text_round_trip(self):
        # GIVEN
        objects = [{"page": 1, "id": 2, "obj": "btn", "text": "{{ name }} ✓"}, {"page": 1, "id": 3, "obj": "label"}]

        # WHEN
        result = objects_from_text(objects_to_text(objects))

        # THEN
        assert result == objects

    def test_text_that_is_not_jsonl_objects_has_none(self):
        assert objects_from_text("hello") == []
        assert objects_from_text('{"page": 1}') == []
        assert objects_from_text('{"obj": "btn"}\n[1]') == []

    def test_empty_lines_are_skipped(self):
        assert objects_from_text('\n{"obj": "btn"}\n\n') == [{"obj": "btn"}]

    def test_with_descendants_adds_the_objects_inside_in_page_order(self):
        # GIVEN
        page = [
            {"id": 1, "obj": "obj"},
            {"id": 2, "obj": "btn", "parentid": 1},
            {"id": 3, "obj": "label", "parentid": 2},
            {"id": 4, "obj": "label"},
        ]

        # WHEN
        result = with_descendants(page, [page[3], page[0]])

        # THEN
        assert result == page

    def test_cascade_moves_repeated_pastes_to_the_same_spot(self):
        cascade = PasteCascade()

        # at the originals, the first paste is moved already
        assert [cascade.next_offset("a", None) for _ in range(3)] == [PASTE_OFFSET, 2 * PASTE_OFFSET, 3 * PASTE_OFFSET]
        # at the mouse, the first paste goes exactly there
        assert [cascade.next_offset("a", (5, 5)) for _ in range(2)] == [0, PASTE_OFFSET]
        assert cascade.next_offset("a", (8, 5)) == 0
        assert cascade.next_offset("b", (8, 5)) == 0

    def test_reset_starts_the_cascade_again(self):
        cascade = PasteCascade()
        cascade.next_offset("a", None)

        cascade.reset()

        assert cascade.next_offset("a", None) == PASTE_OFFSET
