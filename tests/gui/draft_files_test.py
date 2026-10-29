from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.draft.files import (
    SaveConflictError,
    flatten_template_variables,
    plan_save,
    write_save,
)
from tests import TestBase
from tests.helpers import copy_test_config, load_session, write_page

EDITOR_JSONL = """// objects for the editor test
{
  "page": 9,
  "id": 1,
  "obj": "label",
  // from the device vars
  "text": "{{ key_also_present_in_device_vars }}",
  "x": 10,
}
{"page": 9, "id": 2, "obj": "btn", "text": "B"}
"""


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = copy_test_config(tmp_path)
    write_page(root, EDITOR_JSONL)
    return root


class TestDraftFiles(TestBase):
    def test_load_renders_templates_like_a_deployment(self, cfg_root):
        # WHEN
        session = load_session(cfg_root)

        # THEN
        [component] = session.components
        label, button = session.working_objects[component.key]
        assert label["text"] == "test_device_value"
        assert session.is_template(label, "text") is True
        assert component.is_common is False

    def test_files_of_a_relative_config_directory_are_rendered_by_their_resolved_path(self, cfg_root, monkeypatch):
        # GIVEN: the config directory relative to the working directory (`gui -c ./cfg`), and a file outside the draft,
        # which the text editor knows by its resolved path
        monkeypatch.chdir(cfg_root.parent)
        session = load_session(Path(".", cfg_root.name))
        part = (cfg_root / "common" / "parts" / "label.jsonl").resolve()

        # WHEN
        rendered = session.render_text_at(part, "{{ key_also_present_in_device_vars }}")

        # THEN
        assert rendered == "test_device_value"

    def test_parts_of_a_relative_config_directory_are_loaded(self, cfg_root, monkeypatch):
        # GIVEN: the config directory relative to the working directory (`gui -c ./cfg`), and a file that includes a part
        (cfg_root / "common" / "parts").mkdir()
        (cfg_root / "common" / "parts" / "box.jsonl").write_text('{"page": 9, "id": 5, "obj": "obj", "x": 3}\n')
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(
            EDITOR_JSONL + '{"!include": "common/parts/box.jsonl"}\n'
        )
        monkeypatch.chdir(cfg_root.parent)

        # WHEN
        session = load_session(Path(".", cfg_root.name))

        # THEN
        [component] = session.components
        assert [obj["id"] for obj in session.working_objects[component.key]] == [1, 2, 5]
        assert session.include_errors()[component.key] == []

    def test_save_patches_the_source_and_keeps_comments_and_templates(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label, button = session.working_objects[component.key]

        # WHEN
        session.set_source_value(label, "x", 42)
        session.set_source_value(button, "text", "{{ key_also_present_in_device_vars }}")
        session.remove_object(button)
        session.add_object(component.key, {"page": 9, "id": 3, "obj": "label", "text": "new"})
        write_save(plan_save(session))

        # THEN
        content = (cfg_root / "devices" / "test_device" / "editor.jsonl").read_text()
        assert content == (
            "// objects for the editor test\n"
            "{\n"
            '  "page": 9,\n'
            '  "id": 1,\n'
            '  "obj": "label",\n'
            "  // from the device vars\n"
            '  "text": "{{ key_also_present_in_device_vars }}",\n'
            '  "x": 42,\n'
            "}\n"
            '{"page": 9, "id": 3, "obj": "label", "text": "new"}\n'
        )
        # and it loads again
        reloaded = load_session(cfg_root)
        assert [obj["id"] for obj in reloaded.working_objects[component.key]] == [1, 3]

    def test_save_refuses_files_that_changed_on_disk(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        session.set_source_value(session.working_objects[component.key][0], "x", 42)
        component.path.write_text(EDITOR_JSONL + '{"page": 9, "id": 9}\n')

        # THEN
        with pytest.raises(SaveConflictError):
            plan_save(session)

    def test_the_value_of_a_variable_and_a_rendered_text(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components

        # THEN
        assert session.variable_value(component.key, "key_also_present_in_device_vars") == "test_device_value"
        assert session.variable_value(component.key, "p9b2.text") == "B"
        assert session.variable_value(component.key, "device.screen.width") > 0
        with pytest.raises(KeyError):
            session.variable_value(component.key, "no.such.variable")
        assert session.render_text(component.key, "{{ p9b2.text }}!") == "B!"

    def test_computed_variables_in_the_objects_and_in_the_variable_files(self, cfg_root):
        # GIVEN: a variable computed from the screen and another variable
        variable_file = cfg_root / "computed.vars.yaml"
        variable_file.write_text('margin: 4\ncard:\n  w: "{{ device.screen.width - margin * 2 }}"\n')
        session = load_session(cfg_root)
        [component] = session.components

        # THEN: the objects, and a variable file open in the text editor, see the computed value
        assert session.variable_value(component.key, "card.w") == 472
        assert session.variable_value_at(component.path, "card.w") == 472
        assert session.variable_value_at(variable_file, "card.w") == 472
        assert session.render_text_at(variable_file, "{{ device.screen.width - margin * 2 }}") == "472"
        assert session.render_text_at(component.path, "{{ p9b2.text }}") == "B"
        with pytest.raises(KeyError):
            session.variable_value_at(variable_file, "p9b2.text")

    def test_a_page_the_plate_does_not_run_can_not_break_the_others(self, cfg_root):
        # GIVEN: a page with a variable this device doesn't have, in a .cmd file that no startup script runs
        page = cfg_root / "common" / "page" / "unused"
        page.mkdir(parents=True)
        (page / "page.cmd").write_text("run L:/common_page_unused_content.jsonl\n")
        (page / "content.jsonl").write_text('{"page": 8, "id": 1, "obj": "label", "text": "{{ index }}"}\n')
        (page / "vars.yaml").write_text('index: "{{ common.pages.unknown.index }}"\n')

        # WHEN
        session = load_session(cfg_root)

        # THEN
        [component] = session.components
        label, button = session.working_objects[component.key]
        assert label["text"] == "test_device_value"
        assert session.render_text_at(component.path, "{{ p9b2.text }}") == "B"
        assert session.check_template(label, "{{ p8b1.text }}") == "Unknown variable: 'p8b1' is undefined"

    def test_objects_that_refer_to_themselves_and_to_their_page_follow_changes(self, cfg_root):
        # GIVEN
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(
            '{"page": 9, "id": 1, "obj": "label", "x": "{{ b2.x + 5 }}", "h": 20, "w": "{{ this.h * 2 }}"}\n'
            '{"page": 9, "id": 2, "obj": "btn", "x": 10}\n'
        )
        session = load_session(cfg_root)
        [component] = session.components
        label, button = session.working_objects[component.key]
        assert (label["x"], label["w"]) == (15, 40)

        # WHEN
        session.set_source_value(button, "x", 30)
        session.set_source_value(label, "h", 25)

        # THEN
        assert (label["x"], label["w"]) == (35, 50)
        assert session.check_template(label, "{{ this.h + b2.x }}") is None
        assert session.check_template(label, "{{ b3.x }}") == "Unknown variable: 'b3' is undefined"

    def test_suggestions_contain_the_variables_of_a_deployment(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label = session.working_objects[component.key][0]

        # WHEN
        suggestions = dict(session.template_suggestions(label))

        # THEN
        assert suggestions["{{ key_also_present_in_device_vars }}"] == "test_device_value"
        assert suggestions["{{ p9b2.text }}"] == "B"
        assert "{{ device.ip }}" in suggestions

    def test_template_check(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label = session.working_objects[component.key][0]

        # THEN
        assert session.check_template(label, "{{ p9b2.text }}") is None
        assert "Unknown variable" in session.check_template(label, "{{ nope }}")
        assert "Invalid template" in session.check_template(label, "{{ unclosed")

    def test_templates_see_the_objects_of_the_draft(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label, button = session.working_objects[component.key]
        session.set_source_value(button, "w", 50)
        session.set_source_value(label, "w", "{{ p9b2.w }}")
        assert label["w"] == 50 or label["w"] == "50"

        # WHEN
        session.set_source_value(button, "w", 70)

        # THEN
        assert int(label["w"]) == 70
        assert session.check_template(label, "{{ p9b2.w }}") is None
        assert dict(session.template_suggestions(label))["{{ p9b2.w }}"] == 70

    def test_only_objects_that_refer_to_a_changed_object_are_rendered_again(self, cfg_root, monkeypatch):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label, button = session.working_objects[component.key]
        session.set_source_value(button, "w", 50)
        session.set_source_value(label, "w", "{{ p9b2.w }}")
        session.set_source_value(button, "text", "{{ 1 + 1 }}")
        rendered = []
        original = session._renderer.render_object
        monkeypatch.setattr(
            session._renderer,
            "render_object",
            lambda c, source, scope=None: rendered.append(source) or original(c, source, scope),
        )

        # WHEN: the label refers to the button, the button to nothing
        session.set_source_value(button, "w", 33)
        session.set_source_value(label, "x", 5)

        # THEN: the button itself, the label that refers to it, and the label itself; the button is not rendered for the label's change
        assert [source["id"] for source in rendered] == [2, 1, 1]
        assert int(label["w"]) == 33

    def test_objects_that_refer_to_an_object_follow_its_removal_and_new_id(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label, button = session.working_objects[component.key]
        session.set_source_value(label, "text", "{{ p9b2.text }}")
        assert label["text"] == "B"

        # WHEN the button gets another id
        session.set_source_value(button, "id", 7)
        # THEN the label can't find it any more and keeps the template as written
        assert label["text"] == "{{ p9b2.text }}"

        # WHEN it is back and then removed
        session.set_source_value(button, "id", 2)
        assert label["text"] == "B"
        session.remove_object(button)
        assert label["text"] == "{{ p9b2.text }}"

    def test_objects_that_build_the_name_of_the_object_they_refer_to_follow_it(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label, button = session.working_objects[component.key]
        session.set_source_value(button, "w", 50)
        session.set_source_value(label, "w", "{{ p{{ 9 }}b2.w }}")
        assert int(label["w"]) == 50

        # WHEN
        session.set_source_value(button, "w", 70)

        # THEN
        assert int(label["w"]) == 70
        assert session._renderer.referenced_objects(component.key, session.source_of(label)) == {"p9b2"}

    def test_objects_with_a_name_that_can_not_be_resolved_follow_every_change(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components

        # THEN
        assert session._renderer.referenced_objects(component.key, {"w": "{{ p{{ 1 + }}b2.w }}"}) == {"*"}

    def test_undo_renders_the_objects_that_refer_to_the_restored_ones(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label, button = session.working_objects[component.key]
        session.set_source_value(label, "text", "{{ p9b2.text }}")
        session.remove_object(button)
        assert label["text"] == "{{ p9b2.text }}"

        # WHEN the removal is undone
        session.undo()
        # THEN
        assert label["text"] == "B"

        # WHEN the button gets another text, and that is undone
        again = session.working_objects[component.key][1]
        session.set_source_value(again, "text", "C")
        assert label["text"] == "C"
        session.undo()
        # THEN
        assert label["text"] == "B"

    def test_after_saving_the_draft_is_the_files_and_the_history_goes_on(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label, button = session.working_objects[component.key]
        session.set_source_value(label, "x", 42)
        session.remove_object(button)
        session.add_object(component.key, {"page": 9, "id": 3, "obj": "label", "text": "new"})
        changes = plan_save(session)
        write_save(changes)

        # WHEN
        session.mark_saved({change.path: change.content for change in changes})

        # THEN the draft is what loading the files gives
        assert session.is_dirty is False
        assert session.changes() == []
        [saved] = session.components
        loaded = load_session(cfg_root)
        [reloaded] = loaded.components
        assert (saved.content, saved.sources) == (reloaded.content, reloaded.sources)
        # the lines of the objects are those of the saved file, also of the added one
        assert [session.line_of(obj) for obj in session.working_objects[saved.key]] == [
            loaded.line_of(obj) for obj in loaded.working_objects[reloaded.key]
        ]

        # WHEN the saved edits are undone
        session.undo()
        assert [obj["id"] for obj in session.working_objects[saved.key]] == [1]
        assert session.is_dirty is True
        session.undo()
        # THEN the removed button comes back at the end of the file
        assert [obj["id"] for obj in session.working_objects[saved.key]] == [1, 2]
        assert {c.component.key: c for c in session.changes()}[saved.key].additions == [
            {"page": 9, "id": 2, "obj": "btn", "text": "B"}
        ]
        session.undo()
        assert session.working_objects[saved.key][0]["x"] == 10
        assert session.undo() is None

        # WHEN everything is redone
        while session.redo() is not None:
            pass
        # THEN the draft is the saved files again
        assert session.is_dirty is False

    def test_saving_again_after_saving(self, cfg_root):
        # GIVEN
        session = load_session(cfg_root)
        [component] = session.components
        label = session.working_objects[component.key][0]
        session.set_source_value(label, "x", 42)
        changes = plan_save(session)
        write_save(changes)
        session.mark_saved({change.path: change.content for change in changes})

        # WHEN
        session.set_source_value(label, "x", 43)
        write_save(plan_save(session))

        # THEN
        assert '"x": 43' in (cfg_root / "devices" / "test_device" / "editor.jsonl").read_text()

    def test_flatten_template_variables(self):
        assert flatten_template_variables({"a": {"b": 1, "not-an-identifier": 2, "c": [1]}, "d": "x"}) == [
            ("{{ a.b }}", 1),
            ("{{ d }}", "x"),
        ]
