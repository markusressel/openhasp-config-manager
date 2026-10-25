from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.source_buffers import DiskChange, SourceBuffer, SourceBuffers
from tests import TestBase


@pytest.fixture
def path(tmp_path) -> Path:
    file = tmp_path / "a.jsonl"
    file.write_text("one")
    return file


class TestSourceBuffer(TestBase):
    def test_open_reads_the_file(self, path):
        buffer = SourceBuffer.open(path)
        assert (buffer.text, buffer.disk_text, buffer.is_dirty) == ("one", "one", False)

    def test_open_of_a_missing_file_is_empty_and_clean(self, tmp_path):
        buffer = SourceBuffer.open(tmp_path / "new.jsonl")
        assert (buffer.text, buffer.disk_text, buffer.is_dirty) == ("", None, False)
        buffer.set_text("x")
        assert buffer.is_dirty

    def test_clean_buffer_follows_the_file(self, path):
        buffer = SourceBuffer.open(path)
        path.write_text("two")
        assert buffer.on_disk_changed() == DiskChange.RELOADED
        assert (buffer.text, buffer.disk_text) == ("two", "two")

    def test_change_without_a_difference(self, path):
        buffer = SourceBuffer.open(path)
        assert buffer.on_disk_changed() == DiskChange.NONE

    def test_dirty_buffer_conflicts(self, path):
        buffer = SourceBuffer.open(path)
        buffer.set_text("mine")
        path.write_text("two")
        assert buffer.on_disk_changed() == DiskChange.CONFLICT
        assert buffer.conflict and buffer.text == "mine"

    def test_file_that_got_the_text_of_the_buffer_is_no_conflict(self, path):
        buffer = SourceBuffer.open(path)
        buffer.set_text("mine")
        path.write_text("mine")
        assert buffer.on_disk_changed() == DiskChange.NONE
        assert not buffer.is_dirty and not buffer.conflict

    def test_deleted_file(self, path):
        buffer = SourceBuffer.open(path)
        path.unlink()
        assert buffer.on_disk_changed() == DiskChange.DELETED
        assert buffer.text == "one"

    def test_deleted_file_of_a_dirty_buffer_conflicts(self, path):
        buffer = SourceBuffer.open(path)
        buffer.set_text("mine")
        path.unlink()
        assert buffer.on_disk_changed() == DiskChange.CONFLICT

    def test_reload_drops_the_changes(self, path):
        buffer = SourceBuffer.open(path)
        buffer.set_text("mine")
        path.write_text("two")
        buffer.on_disk_changed()
        buffer.reload()
        assert (buffer.text, buffer.is_dirty, buffer.conflict) == ("two", False, False)
        path.unlink()
        buffer.reload()
        assert buffer.text == "" and buffer.disk_text is None

    def test_keep_mine_stays_dirty_until_saved(self, path):
        buffer = SourceBuffer.open(path)
        buffer.set_text("mine")
        path.write_text("two")
        buffer.on_disk_changed()
        buffer.keep_mine()
        assert buffer.is_dirty and not buffer.conflict
        assert buffer.on_disk_changed() == DiskChange.NONE
        assert buffer.save() == "mine"
        assert path.read_text() == "mine"
        assert not buffer.is_dirty

    def test_save_creates_folders(self, tmp_path):
        buffer = SourceBuffer.open(tmp_path / "x" / "y.jsonl")
        buffer.set_text("z")
        buffer.save()
        assert (tmp_path / "x" / "y.jsonl").read_text() == "z"


class TestSourceBuffers(TestBase):
    def test_open_returns_the_same_buffer(self, path, tmp_path):
        buffers = SourceBuffers()
        first = buffers.open(path)
        assert buffers.open(tmp_path / "." / "a.jsonl") is first
        assert path in buffers and len(buffers) == 1
        assert list(buffers) == [first]
        assert buffers.get(path) is first

    def test_dirty_and_close(self, path):
        buffers = SourceBuffers()
        buffer = buffers.open(path)
        assert buffers.dirty() == []
        buffer.set_text("x")
        assert buffers.dirty() == [buffer]
        buffers.close(path)
        assert path not in buffers and buffers.get(path) is None
        buffers.close(path)

    def test_changes_are_reported_for_open_buffers_only(self, path, tmp_path):
        buffers = SourceBuffers()
        buffers.open(path)
        other = tmp_path / "b.jsonl"
        other.write_text("x")
        path.write_text("two")
        assert buffers.on_disk_changed([path, other]) == {path.resolve(): DiskChange.RELOADED}
