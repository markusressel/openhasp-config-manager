import json
import logging
from pathlib import Path

from PyQt6.QtCore import QSettings

from openhasp_config_manager.gui.domain.ui_session import UiSession, from_data, to_data

LOGGER = logging.getLogger(__name__)

# JSON: the resolved path of each config directory -> its UiSession
_SESSIONS_KEY = "session/config_directories"
# before the UiSession: the device selected last, and the config directory it belongs to
_LEGACY_SELECTED_DEVICE_KEY = "devices/selected"
_LEGACY_SELECTED_DEVICE_CONFIG_ROOT_KEY = "devices/selected_config_root"


class UiSessionStore:
    """
    Keeps the UiSession of a config directory in QSettings. Change `session`, then call `save()`.
    """

    def __init__(self, config_root: Path, settings: QSettings):
        self._config_root = str(Path(config_root).resolve())
        self._settings = settings
        self.session = self._load()

    @classmethod
    def in_memory(cls) -> "UiSessionStore":
        """:return: a store that remembers nothing for the next start (e.g. in tests)"""
        store = cls.__new__(cls)
        store._config_root = None
        store._settings = None
        store.session = UiSession()
        return store

    def save(self):
        if self._settings is None:
            return
        sessions = self._stored_sessions()
        sessions[self._config_root] = to_data(self.session)
        self._settings.setValue(_SESSIONS_KEY, json.dumps(sessions))

    def _load(self) -> UiSession:
        stored = self._stored_sessions().get(self._config_root)
        if stored is not None:
            return from_data(UiSession, stored)
        return self._migrate_legacy()

    def _stored_sessions(self) -> dict:
        try:
            sessions = json.loads(self._settings.value(_SESSIONS_KEY, "{}"))
        except (TypeError, json.JSONDecodeError):
            LOGGER.warning("The stored editor session can't be read, starting a new one")
            return {}
        return sessions if isinstance(sessions, dict) else {}

    def _migrate_legacy(self) -> UiSession:
        session = UiSession()
        if self._settings.value(_LEGACY_SELECTED_DEVICE_CONFIG_ROOT_KEY) == self._config_root:
            session.selected_device = self._settings.value(_LEGACY_SELECTED_DEVICE_KEY)
            self._settings.remove(_LEGACY_SELECTED_DEVICE_KEY)
            self._settings.remove(_LEGACY_SELECTED_DEVICE_CONFIG_ROOT_KEY)
            self.session = session
            self.save()
        return session
