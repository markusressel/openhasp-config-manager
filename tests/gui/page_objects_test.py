from collections import OrderedDict

import pytest

from openhasp_config_manager.gui.domain.page_objects import (
    OpenHASPWidgetType,
    count_objects,
    create_object,
    get_navigable_page_indices,
    get_page_objects,
    is_hidden,
    navigate,
    page_label,
    page_settings,
    selectable_pages,
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

    def test_step_page_from_a_page_without_objects_goes_to_the_next_one_in_that_direction(self):
        assert step_page([1, 5, 8], current=3, step=1) == 5
        assert step_page([1, 5, 8], current=3, step=-1) == 1
        assert step_page([1, 5, 8], current=10, step=1) == 1
        assert step_page([2, 5, 8], current=1, step=-1) == 8

    def test_every_page_and_the_global_one_can_be_selected(self):
        assert selectable_pages(3) == list(range(0, 13))
        assert selectable_pages(15) == [*range(0, 13), 15]
        assert page_label(0) == "Global (page 0)"
        assert page_label(4) == "Page 4"

    def test_step_page_without_pages(self):
        assert step_page([], current=1, step=1) is None

    def test_navigable_pages_skip_page_0(self):
        assert get_navigable_page_indices(_draft()) == [1, 2]

    def _limited(self) -> OrderedDict:
        # the pages 1 to 3 are the navigation, 9 is a page of its own
        return OrderedDict(
            [
                (
                    "pages.jsonl",
                    [
                        {"page": 1, "id": 0, "prev": 3},
                        {"page": 3, "id": 0, "next": "1"},
                        {"page": 1, "id": 1, "obj": "label"},
                        {"page": 2, "id": 1, "obj": "label"},
                        {"page": 3, "id": 1, "obj": "label"},
                        {"page": 9, "id": 1, "obj": "label"},
                    ],
                )
            ]
        )

    def test_page_settings_are_the_object_with_id_0(self):
        assert page_settings(self._limited(), 3) == {"page": 3, "id": 0, "next": "1"}
        assert page_settings(self._limited(), 2) == {}

    def test_the_settings_of_a_page_limit_where_the_buttons_lead(self):
        draft = self._limited()
        assert navigate(draft, 3, "next") == 1
        assert navigate(draft, 1, "prev") == 3

    def test_without_a_setting_the_buttons_go_to_the_page_after_and_before_like_on_the_plate(self):
        draft = self._limited()
        # empty pages included, rolling over between 12 and 1
        assert navigate(draft, 2, "next") == 3
        assert navigate(draft, 9, "next") == 10
        assert navigate(draft, 12, "next") == 1
        assert navigate(draft, 2, "prev") == 1
        assert navigate(draft, 9, "prev") == 8
        assert navigate(draft, 1, "prev") == 3  # configured
        assert navigate(OrderedDict(), 1, "prev") == 12

    def test_back_leads_to_the_start_page_unless_configured(self):
        draft = self._limited()
        assert navigate(draft, 2, "back") == 1
        assert navigate(draft, 2, "back", start_page=5) == 5
        draft["pages.jsonl"].append({"page": 2, "id": 0, "back": 3})
        assert navigate(draft, 2, "back", start_page=5) == 3

    def test_invalid_settings_are_ignored(self):
        draft = self._limited()
        draft["pages.jsonl"].append({"page": 2, "id": 0, "next": "x", "prev": 99})
        assert navigate(draft, 2, "next") == 3
        assert navigate(draft, 2, "prev") == 1

    def test_the_global_page_is_no_page_to_navigate_from(self):
        assert navigate(self._limited(), 0, "next") is None

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

    def test_object_without_size_is_not_positioned_and_can_have_a_parent(self):
        # WHEN
        tab = create_object(OpenHASPWidgetType.TAB, page=3, obj_id=5, screen_width=480, screen_height=320, parent_id=2)

        # THEN
        assert (tab["obj"], tab["parentid"]) == ("tab", 2)
        assert "x" not in tab and "y" not in tab
