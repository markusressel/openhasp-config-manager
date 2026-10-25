import pytest

from tests import TestBase
from tests.gui.helpers import wait_until


@pytest.fixture
def watcher(qapp, tmp_path):
    pytest.importorskip("watchdog")
    from openhasp_config_manager.gui.qt.config_watcher import ConfigWatcher

    root = tmp_path / "cfg"
    (root / "devices" / "a").mkdir(parents=True)
    (root / "output").mkdir()
    watcher = ConfigWatcher(root.resolve(), ignored_roots=[(root / "output").resolve()], debounce_ms=100)
    watcher.reported = []
    watcher.changed.connect(watcher.reported.append)
    watcher.start()
    yield watcher
    watcher.stop()


class TestConfigWatcher(TestBase):
    def test_a_burst_of_changes_is_reported_once(self, watcher):
        # GIVEN
        root = watcher._root

        # WHEN
        for i in range(3):
            (root / "devices" / "a" / f"page{i}.jsonl").write_text("{}")

        # THEN
        wait_until(lambda: watcher.reported)
        from PyQt6.QtTest import QTest

        QTest.qWait(300)
        assert len(watcher.reported) == 1
        assert {path.name for path in watcher.reported[0]} == {"page0.jsonl", "page1.jsonl", "page2.jsonl"}

    def test_files_in_subfolders_created_later_are_watched(self, watcher):
        # GIVEN
        folder = watcher._root / "devices" / "b" / "pages"

        # WHEN
        folder.mkdir(parents=True)
        (folder / "x.jsonl").write_text("{}")
        wait_until(lambda: any(path.name == "x.jsonl" for paths in watcher.reported for path in paths))

        # AND
        watcher.reported.clear()
        (folder / "x.jsonl").write_text("{ }")

        # THEN
        wait_until(lambda: watcher.reported)
        assert {path.name for path in watcher.reported[0]} == {"x.jsonl"}

    def test_temporary_files_and_the_output_are_not_reported(self, watcher):
        # GIVEN
        root = watcher._root

        # WHEN
        (root / "devices" / "a" / "page.jsonl.swp").write_text("x")
        (root / "devices" / "a" / "page.jsonl~").write_text("x")
        (root / "output" / "page.jsonl").write_text("x")
        (root / "devices" / "a" / "real.jsonl").write_text("{}")

        # THEN
        wait_until(lambda: watcher.reported)
        assert {path.name for paths in watcher.reported for path in paths} == {"real.jsonl"}

    def test_reading_a_file_is_not_a_change(self, watcher):
        # GIVEN
        file = watcher._root / "devices" / "a" / "page.jsonl"
        file.write_text("{}")
        wait_until(lambda: watcher.reported)
        watcher.reported.clear()

        # WHEN
        file.read_text()
        from PyQt6.QtTest import QTest

        QTest.qWait(400)

        # THEN
        assert watcher.reported == []
