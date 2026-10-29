import pytest

from openhasp_config_manager.gui.domain.ui_session import TabSession
from tests import TestBase


@pytest.fixture
def store_for(settings):
    from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore

    return lambda root: UiSessionStore(root, settings)


class TestUiSessionStore(TestBase):
    def test_a_saved_session_is_loaded_again_for_its_config_directory_only(self, store_for, tmp_path):
        # GIVEN
        store = store_for(tmp_path / "a")
        store.session.selected_device = "plate"
        store.session.device("plate").target_file = "devices/plate/page.jsonl"
        store.session.open_tabs = [TabSession("plate"), TabSession("plate", "common/dot.jsonl", "page.jsonl:2")]
        store.session.active_tab = 1

        # WHEN
        store.save()

        # THEN
        assert store_for(tmp_path / "a" / ".." / "a").session == store.session
        assert store_for(tmp_path / "b").session.selected_device is None

    def test_sessions_of_other_config_directories_are_kept(self, store_for, tmp_path):
        # GIVEN
        a = store_for(tmp_path / "a")
        b = store_for(tmp_path / "b")
        a.session.selected_device = "first"
        a.save()

        # WHEN
        b.session.selected_device = "second"
        b.save()

        # THEN
        assert store_for(tmp_path / "a").session.selected_device == "first"

    def test_the_selection_of_older_versions_is_taken_over(self, store_for, settings, tmp_path):
        # GIVEN
        settings.setValue("devices/selected", "plate")
        settings.setValue("devices/selected_config_root", str(tmp_path.resolve()))

        # WHEN
        store = store_for(tmp_path)

        # THEN
        assert store.session.selected_device == "plate"
        assert settings.value("devices/selected") is None
        assert store_for(tmp_path).session.selected_device == "plate"

    def test_a_broken_stored_value_starts_a_new_session(self, store_for, settings, tmp_path):
        settings.setValue("session/config_directories", "{broken")

        assert store_for(tmp_path).session.selected_device is None

    def test_in_memory_saves_nothing(self, settings):
        from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore

        store = UiSessionStore.in_memory()
        store.session.selected_device = "plate"
        store.save()

        assert settings.allKeys() == []
