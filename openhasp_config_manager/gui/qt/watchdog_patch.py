import os

from watchdog.utils import platform
from watchdog.version import VERSION_STRING

_AFFECTED_VERSION = "7.0.0"


def apply_watchdog_patch():
    """
    Backport of https://github.com/gorakhargosh/watchdog/pull/1388 (released with watchdog 7.1.0), `_recursive_simulate` of
    `InotifyWatchGroup`. A folder that appears while the watches of a new folder are added (`cp -r`, `mkdir -p` of a tool, the
    preview images of the GUI itself) has no watch yet, the lookup of 7.0.0 raises a `KeyError` in the only inotify thread of the
    process, and from then on no observer reports anything. Remove this module when 7.1.0 is the minimum version.
    """
    if VERSION_STRING != _AFFECTED_VERSION or not platform.is_linux():
        return

    from watchdog.observers.inotify import InotifyWatchGroup
    from watchdog.observers.inotify_c import InotifyConstants, InotifyEvent

    def _recursive_simulate(self, src_path: bytes) -> list[InotifyEvent]:
        events = []
        for root, dirnames, filenames in os.walk(src_path, followlinks=self.follow_symlink):
            wd_root = self._active_callbacks_by_path.get(root)
            if wd_root is None:
                # not watched yet: its own queued IN_CREATE event will watch it and report its content
                continue

            for dirname in dirnames:
                events.append(InotifyEvent(wd_root, InotifyConstants.IN_CREATE | InotifyConstants.IN_ISDIR, 0, dirname))
            for filename in filenames:
                events.append(InotifyEvent(wd_root, InotifyConstants.IN_CREATE, 0, filename))
        return events

    InotifyWatchGroup._recursive_simulate = _recursive_simulate
