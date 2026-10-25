from openhasp_config_manager.gui.domain.edit_history import EditHistory
from tests import TestBase


class TestEditHistory(TestBase):
    def test_undo_and_redo_return_the_steps_in_order(self):
        # GIVEN
        history = EditHistory()
        history.push("first", 0, 1)
        history.push("second", 1, 2)

        # WHEN
        undone = [history.undo(), history.undo(), history.undo()]

        # THEN
        assert [(step.description, step.before) for step in undone[:2]] == [("second", 1), ("first", 0)]
        assert undone[2] is None
        assert history.redo().after == 1
        assert history.redo().after == 2
        assert history.redo() is None

    def test_descriptions(self):
        history = EditHistory()
        assert (history.undo_description, history.redo_description) == (None, None)
        history.push("move", 0, 1)
        assert (history.undo_description, history.redo_description) == ("move", None)
        history.undo()
        assert (history.undo_description, history.redo_description) == (None, "move")

    def test_an_edit_drops_what_could_be_redone(self):
        # GIVEN
        history = EditHistory()
        history.push("first", 0, 1)
        history.undo()

        # WHEN
        history.push("other", 0, 5)

        # THEN
        assert history.redo() is None
        assert history.undo().description == "other"

    def test_edits_with_the_same_merge_key_are_one_step(self):
        # GIVEN
        history = EditHistory()
        history.push("other", 0, 1, merge_key="b")

        # WHEN typing into a property
        for value in [2, 3, 4]:
            history.push("text", value - 1, value, merge_key="a")

        # THEN
        step = history.undo()
        assert (step.description, step.before, step.after) == ("text", 1, 4)
        assert history.undo().description == "other"

    def test_merged_edits_back_to_the_start_leave_nothing_to_undo(self):
        # GIVEN
        history = EditHistory()
        history.push("first", 0, 1)
        history.push("nudge", 1, 2, merge_key="nudge")

        # WHEN
        history.push("nudge", 2, 1, merge_key="nudge")

        # THEN
        assert history.undo().description == "first"

    def test_a_sealed_step_is_not_merged(self):
        # GIVEN
        history = EditHistory()
        history.push("text", 0, 1, merge_key="a")

        # WHEN e.g. another object was selected in between
        history.seal()
        history.push("text", 1, 2, merge_key="a")

        # THEN
        assert history.undo().before == 1
        assert history.undo().before == 0

    def test_a_redone_step_is_not_merged(self):
        # GIVEN
        history = EditHistory()
        history.push("text", 0, 1, merge_key="a")
        history.undo()
        history.redo()

        # WHEN
        history.push("text", 1, 2, merge_key="a")

        # THEN
        assert history.undo().before == 1

    def test_only_the_last_steps_are_kept(self):
        # GIVEN
        history = EditHistory(limit=2)

        # WHEN
        for value in range(3):
            history.push(f"edit {value}", value, value + 1)

        # THEN
        assert [history.undo().description, history.undo().description, history.undo()] == ["edit 2", "edit 1", None]

    def test_clear(self):
        history = EditHistory()
        history.push("first", 0, 1)
        history.push("second", 1, 2)
        history.undo()

        history.clear()

        assert (history.undo(), history.redo()) == (None, None)

    def test_mapped_translates_every_state(self):
        # GIVEN
        history = EditHistory()
        history.push("first", 0, 1)
        history.push("second", 1, 2)
        history.undo()

        # WHEN
        mapped = history.mapped(lambda state: state * 10)

        # THEN
        assert mapped.redo().after == 20
        assert [mapped.undo().before, mapped.undo().before] == [10, 0]
        # the original is unchanged
        assert history.redo().after == 2
