"""Helpers of the tests that need a config directory to change, and the draft of its device (all without Qt)."""

import shutil
from pathlib import Path
from typing import Mapping

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.draft.files import load_device
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.manager import ConfigManager

# the test config, never changed by a test: copy it (`copy_test_config`) to change it
TEST_CFG_ROOT = Path(__file__).parent / "_test_cfg_root"
TEST_DEVICE = "test_device"
DEVICE_DIR = f"devices/{TEST_DEVICE}"


def copy_test_config(tmp_path: Path, files: Mapping[str, str] = {}) -> Path:
    """
    :param files: files to write into the copy: path relative to the config directory -> content (folders are created)
    :return: a copy of the test config, `tmp_path / "cfg"`
    """
    root = tmp_path / "cfg"
    shutil.copytree(TEST_CFG_ROOT, root)
    for path, content in files.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
    return root


def write_page(cfg_root: Path, jsonl: str, name: str = "editor.jsonl") -> Path:
    """:return: a file of the test device, the only one its `boot.cmd` runs"""
    file = cfg_root / DEVICE_DIR / name
    file.write_text(jsonl)
    (cfg_root / DEVICE_DIR / "boot.cmd").write_text(f"run L:/{name}\n")
    return file


def create_config_manager(cfg_root: Path) -> ConfigManager:
    """A manager of the config directory, with an output directory next to it."""
    return _create_config_manager(cfg_root, cfg_root.parent / "output")


def load_session(cfg_root: Path, device: str = TEST_DEVICE) -> PlateSession:
    """:return: the draft of the device, loaded from the files like the GUI does"""
    loaded = load_device(create_config_manager(cfg_root), device)
    session = PlateSession(device=loaded.device)
    session.load(loaded.components, loaded.renderer)
    return session
