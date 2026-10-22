from collections import OrderedDict

import pytest

from openhasp_config_manager.gui.domain.page_objects import (
    OpenHASPWidgetType,
    count_objects,
    create_object,
    get_navigable_page_indices,
    get_page_objects,
    is_hidden,
    step_page,
    is_id_used,
    next_free_id,
)
from tests import TestBase


def _draft() -> OrderedDict:
    return OrderedDict(
        [
            ("nav.jsonl", [{"page": 0, "id": 1, "obj": "btn"}]),
            (
                "home.jsonl",
                [
                    {"page": 1, "id": 1, "obj": "label"},
                    {"page": 1, "id": 2, "obj": "btn", "hidden": True},
                    {"page": 2, "id": 1, "obj": "label"},
                ],
            ),
            ("empty.jsonl", []),
        ]
    )


class TestPageObjects(TestBase):
    def test_page_objects_include_hidden_and_global_objects_last(self):
        # WHEN
        result = get_page_objects(_draft(), index=1)

        # THEN
        assert [(obj["page"], obj["id"]) for obj in result] == [(1, 1), (1, 2), (0, 1)]

    def test_page_objects_without_global_objects(self):
        # WHEN
        result = get_page_objects(_draft(), index=2, include_global=False)

        # THEN
        assert [(obj["page"], obj["id"]) for obj in result] == [(2, 1)]

    def test_is_hidden(self):
        assert is_hidden({"hidden": True}) is True
        assert is_hidden({"hidden": 1}) is True
        assert is_hidden({"hidden": "true"}) is True
        assert is_hidden({"hidden": False}) is False
        assert is_hidden({"hidden": 0}) is False
        assert is_hidden({}) is False

    def test_step_page_rolls_over(self):
        assert step_page([1, 2, 5], current=5, step=1) == 1
        assert step_page([1, 2, 5], current=1, step=-1) == 5
        assert step_page([1, 2, 5], current=2, step=1) == 5

    def test_step_page_from_a_page_without_objects_goes_to_the_first(self):
        assert step_page([1, 2], current=42, step=1) == 1

    def test_step_page_without_pages(self):
        assert step_page([], current=1, step=1) is None

    def test_navigable_pages_skip_page_0(self):
        assert get_navigable_page_indices(_draft()) == [1, 2]

    def test_count_objects(self):
        assert count_objects(_draft()) == 4

    def test_next_free_id_fills_gaps(self):
        # GIVEN
        draft = _draft()
        draft["home.jsonl"].append({"page": 1, "id": 4, "obj": "label"})

        # THEN
        assert next_free_id(draft, page=1) == 3
        assert next_free_id(draft, page=7) == 1

    def test_next_free_id_raises_when_page_is_full(self):
        # GIVEN
        draft = OrderedDict([("a.jsonl", [{"page": 1, "id": i} for i in range(1, 255)])])

        # THEN
        with pytest.raises(ValueError):
            next_free_id(draft, page=1)

    def test_id_used_ignores_the_object_itself(self):
        # GIVEN
        draft = _draft()
        label = draft["home.jsonl"][0]

        # THEN
        assert is_id_used(draft, page=1, obj_id=1, ignore=label) is False
        assert is_id_used(draft, page=1, obj_id=2, ignore=label) is True
        assert is_id_used(draft, page=2, obj_id=2, ignore=label) is False

    def test_create_object_is_centered(self):
        # WHEN
        obj = create_object(OpenHASPWidgetType.BUTTON, page=3, obj_id=5, screen_width=480, screen_height=320)

        # THEN
        assert obj["obj"] == "btn"
        assert (obj["page"], obj["id"]) == (3, 5)
        assert obj["x"] == (480 - obj["w"]) // 2
        assert obj["y"] == (320 - obj["h"]) // 2
