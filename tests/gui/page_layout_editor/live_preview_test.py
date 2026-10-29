

from tests import TestBase
from tests.gui.helpers import wait_until
from tests.gui.page_layout_editor.helpers import _key, _object, _sent_objects


class TestLivePreview(TestBase):
    def _start(self, editor, plate):
        editor.plate.action_live_preview.setChecked(True)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))

    def test_turning_it_on_sends_the_page_and_shows_it(self, editor, plate):
        # WHEN
        self._start(editor, plate)

        # THEN
        calls = plate.calls
        assert calls[0] == ("clear_page", 9)
        assert {(9, 1), (9, 2)} <= set(_sent_objects(plate))
        assert calls[-1] == ("set_page", 9)

    def test_an_edit_sends_only_the_changed_property(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.session.set_source_value(_object(editor, 1), "x", 20)

        # THEN
        wait_until(lambda: plate.calls)
        assert plate.calls == [("jsonl", {"page": 9, "id": 1, "x": 20})]

    def test_fast_edits_are_coalesced_and_the_last_one_is_sent(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()
        label = _object(editor, 1)

        # WHEN
        for x in range(20, 30):
            editor.session.set_source_value(label, "x", x)

        # THEN
        wait_until(lambda: plate.calls and plate.calls[-1] == ("jsonl", {"page": 9, "id": 1, "x": 29}))
        assert len(plate.calls) == 2

    def test_removing_an_object_deletes_it(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.session.remove_object(_object(editor, 2))

        # THEN
        wait_until(lambda: plate.calls)
        assert plate.calls == [("delete_object_id", 9, 2)]

    def _go_to(self, editor, plate, index: int):
        editor._go_to_page(index)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", index))

    def test_a_page_that_was_sent_before_is_only_shown(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        self._go_to(editor, plate, 1)
        assert ("clear_page", 1) in plate.calls
        plate.clear()

        # WHEN
        self._go_to(editor, plate, 9)

        # THEN
        assert plate.calls == [("set_page", 9)]

    def test_changes_of_a_page_that_is_not_shown_are_sent_when_it_is(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        self._go_to(editor, plate, 1)
        self._go_to(editor, plate, 9)
        plate.clear()

        # WHEN
        label = next(obj for obj in editor.session.working_objects[_key(editor, "editor.jsonl")] if obj.get("id") == 50)
        editor.session.set_source_value(label, "x", 7)
        self._go_to(editor, plate, 1)

        # THEN
        assert plate.calls == [("jsonl", {"page": 1, "id": 50, "x": 7}), ("set_page", 1)]

    def test_objects_removed_from_a_page_that_is_not_shown_are_deleted_when_it_is(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        self._go_to(editor, plate, 1)
        self._go_to(editor, plate, 9)
        plate.clear()

        # WHEN
        label = next(obj for obj in editor.session.working_objects[_key(editor, "editor.jsonl")] if obj.get("id") == 50)
        editor.session.remove_object(label)
        self._go_to(editor, plate, 1)

        # THEN
        assert plate.calls == [("delete_object_id", 1, 50), ("set_page", 1)]

    def test_a_page_the_editor_left_before_it_was_sent_is_not_sent(self, editor, plate, async_loop):
        # GIVEN: the plate is busy with something else, so the sends wait (in order) until the editor is back on page 9
        import asyncio

        lock = editor.plate._send_lock
        asyncio.run_coroutine_threadsafe(lock.acquire(), async_loop).result(timeout=5)
        editor.plate.action_live_preview.setChecked(True)

        # WHEN
        editor._go_to_page(1)
        editor._go_to_page(9)
        async_loop.call_soon_threadsafe(lock.release)

        # THEN: page 9 was sent once and shown twice, page 1 not at all
        wait_until(lambda: not editor.busy.busy)
        assert ("clear_page", 1) not in plate.calls
        assert plate.calls.count(("clear_page", 9)) == 1
        assert plate.calls.count(("set_page", 9)) == 2

    def test_forgotten_pages_are_sent_in_full_again(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        self._go_to(editor, plate, 1)
        plate.clear()

        # WHEN: e.g. the plate restarted
        editor.plate.forget_sent()
        self._go_to(editor, plate, 9)

        # THEN
        assert plate.calls[0] == ("clear_page", 9)

    def test_clear_page_is_disabled_while_it_is_on(self, editor, plate):
        # WHEN
        self._start(editor, plate)

        # THEN
        assert editor.plate.action_clear.isEnabled() is False

    def test_stopping_silently_sends_nothing_more(self, editor, plate):
        # GIVEN
        self._start(editor, plate)
        plate.clear()

        # WHEN
        editor.plate.stop_live_preview()
        editor.session.set_source_value(_object(editor, 1), "x", 20)

        # THEN
        from PyQt6.QtTest import QTest

        QTest.qWait(150)
        assert plate.calls == []
        assert editor.plate.live is False


class TestRestorePlate(TestBase):
    def test_restore_ends_live_preview_and_rebuilds_the_plate_from_its_files(self, editor, plate):
        # GIVEN
        restored = []
        editor.plate.plateRestored.connect(lambda: restored.append(True))
        editor.plate.action_live_preview.setChecked(True)
        wait_until(lambda: plate.calls and plate.calls[-1] == ("set_page", 9))
        plate.clear()

        # WHEN
        editor.plate.restore_plate()

        # THEN
        wait_until(lambda: restored)
        assert plate.calls == [("restore_from_files",)]
        assert editor.plate.live is False
