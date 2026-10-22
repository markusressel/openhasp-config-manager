import shutil
from pathlib import Path

import pytest

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.draft_files import (
    SaveConflictError,
    flatten_template_variables,
    load_device,
    plan_save,
    write_save,
)
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from tests import TestBase

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
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    device = root / "devices" / "test_device"
    (device / "editor.jsonl").write_text(EDITOR_JSONL)
    (device / "boot.cmd").write_text("run L:/editor.jsonl\n")
    return root


def _load(cfg_root: Path) -> PlateSession:
    loaded = load_device(_create_config_manager(cfg_root, cfg_root.parent / "output"), "test_device")
    session = PlateSession(device=loaded.device)
    session.load(loaded.components, loaded.renderer)
    return session


class TestDraftFiles(TestBase):
    def test_load_renders_templates_like_a_deployment(self, cfg_root):
        # WHEN
        session = _load(cfg_root)

        # THEN
        [component] = session.components
        label, button = session.working_objects[component.key]
        assert label["text"] == "test_device_value"
        assert session.is_template(label, "text") is True
        assert component.is_common is False

    def test_save_patches_the_source_and_keeps_comments_and_templates(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
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
        reloaded = _load(cfg_root)
        assert [obj["id"] for obj in reloaded.working_objects[component.key]] == [1, 3]

    def test_save_refuses_files_that_changed_on_disk(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
        [component] = session.components
        session.set_source_value(session.working_objects[component.key][0], "x", 42)
        component.path.write_text(EDITOR_JSONL + '{"page": 9, "id": 9}\n')

        # THEN
        with pytest.raises(SaveConflictError):
            plan_save(session)

    def test_suggestions_contain_the_variables_of_a_deployment(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
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
        session = _load(cfg_root)
        [component] = session.components
        label = session.working_objects[component.key][0]

        # THEN
        assert session.check_template(label, "{{ p9b2.text }}") is None
        assert "Unknown variable" in session.check_template(label, "{{ nope }}")
        assert "Invalid template" in session.check_template(label, "{{ unclosed")

    def test_templates_see_the_objects_of_the_draft(self, cfg_root):
        # GIVEN
        session = _load(cfg_root)
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

    def test_flatten_template_variables(self):
        assert flatten_template_variables({"a": {"b": 1, "not-an-identifier": 2, "c": [1]}, "d": "x"}) == [
            ("{{ a.b }}", 1),
            ("{{ d }}", "x"),
        ]
