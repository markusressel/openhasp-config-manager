import shutil
from pathlib import Path

import pytest

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase

PAGE = Path("devices", "test_device", "home", "page.jsonl")


class TestReferencedFiles(TestBase):
    @pytest.fixture
    def cfg(self, tmp_path) -> Path:
        cfg = Path(tmp_path, "cfg")
        shutil.copytree(self.cfg_root, cfg)
        return cfg

    @staticmethod
    def _add_object(cfg: Path, **properties):
        with Path(cfg, PAGE).open("a") as file:
            file.write("\n" + str(properties).replace("'", '"').replace("True", "true") + "\n")

    @staticmethod
    def _add_file(cfg: Path, path: str, content: bytes = b"data"):
        file = Path(cfg, "devices", "test_device", path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)

    @staticmethod
    def _relevant_names(cfg: Path, tmp_path: Path):
        manager = ConfigManager(cfg, Path(tmp_path, "out"), VariableManager(cfg))
        device = manager.analyze()[0]
        return {c.name for c in manager.find_relevant_components(device)}

    def test_truetype_font_is_copied_with_its_size_in_the_reference(self, cfg, tmp_path):
        self._add_file(cfg, "fonts/arial.ttf")
        self._add_file(cfg, "fonts/unused.ttf")
        self._add_object(cfg, page=1, id=20, obj="label", text_font="fonts_arial20")

        names = self._relevant_names(cfg, tmp_path)

        assert "fonts_arial.ttf" in names
        assert "fonts_unused.ttf" not in names

    def test_binary_font_is_copied(self, cfg, tmp_path):
        self._add_file(cfg, "fonts/arial_20.bin")
        self._add_object(cfg, page=1, id=20, obj="label", text_font="fonts_arial_20")

        assert "fonts_arial_20.bin" in self._relevant_names(cfg, tmp_path)

    def test_font_reference_without_a_file_is_not_an_error(self, cfg, tmp_path):
        self._add_object(cfg, page=1, id=20, obj="label", text_font="on_the_plate20")

        assert self._relevant_names(cfg, tmp_path)

    def test_image_with_a_name_from_a_template_is_copied(self, cfg, tmp_path):
        self._add_file(cfg, "icons/home.png")
        Path(cfg, "devices", "test_device", "icons.yaml").write_text("icon: icons_home\n")
        self._add_object(cfg, page=1, id=20, obj="img", src="L:/{{ icon }}.png")

        assert "icons_home.png" in self._relevant_names(cfg, tmp_path)

    def test_missing_image_names_the_file_that_refers_to_it(self, cfg, tmp_path):
        self._add_object(cfg, page=1, id=20, obj="img", src="L:/nope.png")

        with pytest.raises(AssertionError, match=r"nope.png.*page.jsonl"):
            self._relevant_names(cfg, tmp_path)

    def test_included_files_are_copied_without_a_reference(self, cfg, tmp_path):
        self._add_file(cfg, "icons/for_mqtt.png")
        self._add_file(cfg, "icons/other.png")
        self._add_file(cfg, "fonts/mqtt.ttf")
        Path(cfg, "devices", "test_device", "include.yaml").write_text(
            "include_files:\n  - icons_for_*.png\n  - fonts_mqtt.ttf\n"
        )

        names = self._relevant_names(cfg, tmp_path)

        assert {"icons_for_mqtt.png", "fonts_mqtt.ttf"} <= names
        assert "icons_other.png" not in names

    def test_include_files_can_be_set_for_all_devices(self, cfg, tmp_path):
        self._add_file(cfg, "icons/other.png")
        Path(cfg, "include.yaml").write_text("include_files: icons_other.png\n")

        assert "icons_other.png" in self._relevant_names(cfg, tmp_path)

    def test_include_files_must_be_a_list_of_patterns(self, cfg, tmp_path):
        Path(cfg, "include.yaml").write_text("include_files: {a: b}\n")

        with pytest.raises(ValueError, match="include_files"):
            self._relevant_names(cfg, tmp_path)

    def test_font_files_are_deployed(self, cfg, tmp_path):
        self._add_file(cfg, "fonts/arial.ttf", b"font")
        self._add_object(cfg, page=1, id=20, obj="label", text_font="fonts_arial20")
        manager = ConfigManager(cfg, Path(tmp_path, "out"), VariableManager(cfg))

        manager.process(manager.analyze()[0])

        assert Path(tmp_path, "out", "test_device", "fonts_arial.ttf").read_bytes() == b"font"
