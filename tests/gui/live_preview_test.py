from openhasp_config_manager.gui.domain.live_preview import LivePage, LiveUpdate
from tests import TestBase


def _button(id: int = 1, **properties):
    return {"page": 1, "id": id, "obj": "btn", "x": 0, "y": 0, "text": "A", **properties}


class TestLivePage(TestBase):
    def test_nothing_changed(self):
        page = LivePage()
        page.reset([_button()])

        assert page.update([_button()]) is None

    def test_changed_property_sends_only_that_property(self):
        page = LivePage()
        page.reset([_button()])

        assert page.update([_button(x=10)]) == LiveUpdate(objects=[{"page": 1, "id": 1, "x": 10}])

    def test_new_property_is_sent(self):
        page = LivePage()
        page.reset([_button()])

        assert page.update([_button(hidden=1)]) == LiveUpdate(objects=[{"page": 1, "id": 1, "hidden": 1}])

    def test_new_object_is_sent_in_full(self):
        page = LivePage()
        page.reset([_button(1)])

        assert page.update([_button(1), _button(2)]) == LiveUpdate(objects=[_button(2)])

    def test_removed_object_is_deleted(self):
        page = LivePage()
        page.reset([_button(1), _button(2)])

        assert page.update([_button(1)]) == LiveUpdate(deletions=[(1, 2)])

    def test_changed_id_deletes_the_old_and_sends_the_new_object(self):
        page = LivePage()
        page.reset([_button(1)])

        assert page.update([_button(5)]) == LiveUpdate(deletions=[(1, 1)], objects=[_button(5)])

    def test_removed_property_resends_the_page(self):
        page = LivePage()
        page.reset([_button(hidden=1)])

        assert page.update([_button()]) == LiveUpdate(resend_page=True)

    def test_changed_type_resends_the_page(self):
        page = LivePage()
        page.reset([_button()])

        assert page.update([_button(obj="label")]) == LiveUpdate(resend_page=True)

    def test_sent_state_follows_the_updates(self):
        page = LivePage()
        page.reset([_button()])
        page.update([_button(x=10)])

        assert page.update([_button(x=10)]) is None
        assert page.update([_button(x=20)]) == LiveUpdate(objects=[{"page": 1, "id": 1, "x": 20}])

    def test_later_changes_of_the_objects_are_not_mistaken_for_sent(self):
        page = LivePage()
        obj = _button()
        page.reset([obj])

        # the editor changes the rendered objects in place
        obj["x"] = 10

        assert page.update([obj]) == LiveUpdate(objects=[{"page": 1, "id": 1, "x": 10}])
