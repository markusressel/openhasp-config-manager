from openhasp_config_manager.gui.domain.live_preview import MAX_LIVE_PREVIEWS, LivePlate, LiveUpdate, live_preview_refusal
from tests import TestBase


def _button(id: int = 1, **properties):
    return {"page": 1, "id": id, "obj": "btn", "x": 0, "y": 0, "text": "A", **properties}


class TestLivePlate(TestBase):
    def test_nothing_changed(self):
        plate = LivePlate()
        plate.reset(1, [_button()])

        assert plate.update(1, [_button()]) is None

    def test_changed_property_sends_only_that_property(self):
        plate = LivePlate()
        plate.reset(1, [_button()])

        assert plate.update(1, [_button(x=10)]) == LiveUpdate(objects=[{"page": 1, "id": 1, "x": 10}])

    def test_new_property_is_sent(self):
        plate = LivePlate()
        plate.reset(1, [_button()])

        assert plate.update(1, [_button(hidden=1)]) == LiveUpdate(objects=[{"page": 1, "id": 1, "hidden": 1}])

    def test_new_object_is_sent_in_full(self):
        plate = LivePlate()
        plate.reset(1, [_button(1)])

        assert plate.update(1, [_button(1), _button(2)]) == LiveUpdate(objects=[_button(2)])

    def test_removed_object_is_deleted(self):
        plate = LivePlate()
        plate.reset(1, [_button(1), _button(2)])

        assert plate.update(1, [_button(1)]) == LiveUpdate(deletions=[(1, 2)])

    def test_changed_id_deletes_the_old_and_sends_the_new_object(self):
        plate = LivePlate()
        plate.reset(1, [_button(1)])

        assert plate.update(1, [_button(5)]) == LiveUpdate(deletions=[(1, 1)], objects=[_button(5)])

    def test_removed_property_resends_the_page(self):
        plate = LivePlate()
        plate.reset(1, [_button(hidden=1)])

        assert plate.update(1, [_button()]) == LiveUpdate(resend_page=True)

    def test_changed_type_resends_the_page(self):
        plate = LivePlate()
        plate.reset(1, [_button()])

        assert plate.update(1, [_button(obj="label")]) == LiveUpdate(resend_page=True)

    def test_sent_state_follows_the_updates(self):
        plate = LivePlate()
        plate.reset(1, [_button()])
        plate.update(1, [_button(x=10)])

        assert plate.update(1, [_button(x=10)]) is None
        assert plate.update(1, [_button(x=20)]) == LiveUpdate(objects=[{"page": 1, "id": 1, "x": 20}])

    def test_later_changes_of_the_objects_are_not_mistaken_for_sent(self):
        plate = LivePlate()
        obj = _button()
        plate.reset(1, [obj])

        # the editor changes the rendered objects in place
        obj["x"] = 10

        assert plate.update(1, [obj]) == LiveUpdate(objects=[{"page": 1, "id": 1, "x": 10}])

    def test_a_page_that_was_not_sent_in_full_is_sent_in_full(self):
        plate = LivePlate()
        plate.reset(1, [_button()])

        assert plate.update(2, [_button(page=2)]) == LiveUpdate(resend_page=True)

    def test_a_page_sent_before_keeps_its_objects_while_another_one_is_shown(self):
        plate = LivePlate()
        plate.reset(1, [_button()])
        plate.reset(2, [_button(page=2)])

        assert plate.update(2, [_button(page=2, x=5)]) == LiveUpdate(objects=[{"page": 2, "id": 1, "x": 5}])
        assert plate.update(1, [_button()]) is None
        assert plate.update(1, [_button(x=10)]) == LiveUpdate(objects=[{"page": 1, "id": 1, "x": 10}])

    def test_the_global_objects_are_sent_once_for_all_pages(self):
        # GIVEN: an object of page 0, which is on every page
        plate = LivePlate()
        plate.reset(1, [_button(page=0), _button(2)])
        plate.reset(2, [_button(page=0), _button(2, page=2)])

        # WHEN: it changes while page 2 is shown
        update = plate.update(2, [_button(page=0, x=5), _button(2, page=2)])

        # THEN: and is not sent again with page 1
        assert update == LiveUpdate(objects=[{"page": 0, "id": 1, "x": 5}])
        assert plate.update(1, [_button(page=0, x=5), _button(2)]) is None

    def test_a_page_that_needs_to_be_sent_in_full_is_not_known_until_it_was(self):
        plate = LivePlate()
        plate.reset(1, [_button(hidden=1)])

        assert plate.update(1, [_button()]) == LiveUpdate(resend_page=True)
        assert plate.update(1, [_button()]) == LiveUpdate(resend_page=True)

        plate.reset(1, [_button()])
        assert plate.update(1, [_button()]) is None

    def test_a_removed_global_object_is_deleted_once_for_all_pages(self):
        # GIVEN
        plate = LivePlate()
        plate.reset(1, [_button(page=0), _button(2)])
        plate.reset(2, [_button(page=0), _button(2, page=2)])

        # WHEN: it is removed while page 2 is shown
        update = plate.update(2, [_button(2, page=2)])

        # THEN
        assert update == LiveUpdate(deletions=[(0, 1)])
        assert plate.update(1, [_button(2)]) is None

    def test_an_object_moved_to_another_page_is_deleted_from_its_old_page_when_that_is_shown(self):
        # GIVEN
        plate = LivePlate()
        plate.reset(1, [_button(2)])
        plate.reset(2, [])

        # WHEN
        update = plate.update(2, [_button(2, page=2)])

        # THEN
        assert update == LiveUpdate(objects=[_button(2, page=2)])
        assert plate.update(1, []) == LiveUpdate(deletions=[(1, 2)])


class TestLivePreviewLimit(TestBase):
    def test_up_to_ten_devices(self):
        # GIVEN
        others = [f"plate_{index}" for index in range(MAX_LIVE_PREVIEWS)]

        # THEN
        assert MAX_LIVE_PREVIEWS == 10
        assert live_preview_refusal("new", others[:-1]) is None
        refusal = live_preview_refusal("new", others)
        assert refusal is not None
        assert all(name in refusal for name in others)
