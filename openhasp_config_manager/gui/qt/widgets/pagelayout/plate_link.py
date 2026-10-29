import asyncio
import copy
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QMessageBox, QWidget

from openhasp_config_manager.gui.domain.draft.model import DraftChange
from openhasp_config_manager.gui.domain.draft.page_objects import get_page_objects
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.live_preview import LivePlate, LiveUpdate
from openhasp_config_manager.gui.qt.async_bridge import qBridge, run_async
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.operations import OperationStatus, error_text, run_busy
from openhasp_config_manager.gui.qt.throttle import LatestValueThrottle
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

if TYPE_CHECKING:
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget

# delay between two objects when sending a whole page, to avoid overwhelming the device
SEND_DELAY_SECONDS = 0.1
# Live preview sends the changes of the draft at most this often, e.g. while dragging an object
LIVE_PREVIEW_INTERVAL_MS = 50

RESTORE_PLATE_HINT = "Values sent by haad or Home Assistant appear again with their next update."


class PlateLink(QtCore.QObject):
    """
    What the editors of a device do on its plate: *Live preview* (the draft on the plate while editing), *Clear page* and
    *Restore plate*, with their actions. Everything is sent in order: a page that is sent in full, then the changes after it.

    A plate shows one page, so a device has one link, shared by its tabs (`MainWindow`, see `PlateConnections`): it sends the
    page of one of their editors, its view (`set_view`): the tab of the device that was active last. Live preview keeps
    running while the tabs of the device are in the background: it follows the draft of its view, which also reports the
    edits made through another tab or device of a file both show (a shared part).

    Live preview remembers what it sent to each page (`LivePlate`): coming back to a page only sends what changed since,
    and then shows it. What to send is decided when it is its turn to be sent (in the asyncio thread, under `_send_lock`),
    so that a page the editor already left again is not sent at all.
    """

    # a page on the device may differ from what it should show: sending it failed, or it was cleared
    pageOutOfSync = QtCore.pyqtSignal(int)
    # the plate shows the page of the draft
    pageDeployed = QtCore.pyqtSignal(int)
    # the plate shows its files again
    plateRestored = QtCore.pyqtSignal()
    # Live preview was turned on or off
    liveChanged = QtCore.pyqtSignal(bool)

    def __init__(self, parent: QWidget, status: OperationStatus, view: Optional["PageLayoutEditorWidget"] = None):
        """
        :param parent: the parent of the questions asked while there is no view
        :param view: the editor whose page is sent (see `set_view`)
        """
        super().__init__(parent)
        self._parent = parent
        self._status = status
        self._view: Optional["PageLayoutEditorWidget"] = None

        # what was sent to the pages of the plate. Only used under `_send_lock`; replaced to forget it
        self._live_plate = LivePlate()
        # the page that Live preview shows: a page the editor left before it was sent is not sent
        self._live_index: Optional[int] = None
        # the changes of the draft that wait to be sent
        self._live_throttle = LatestValueThrottle(
            lambda _: self._send_live_changes(), interval_ms=LIVE_PREVIEW_INTERVAL_MS, parent=self
        )
        self._stopping_silently = False
        # the draft whose changes Live preview sends
        self._session: Optional[PlateSession] = None
        # says why Live preview can't be turned on now, None if it can (see `set_live_guard`)
        self._live_guard: Callable[[], Optional[str]] = lambda: None
        # keeps what is sent to the plate in order: a page that is sent in full, then the changes after it
        self._send_lock = asyncio.Lock()

        create = UiComponents.create_action
        self.action_live_preview = create(
            parent,
            "Live preview",
            "broadcast",
            tooltip="Show the draft on the plate while you edit it: the page of the editor and every change are sent "
            "right away.\nNothing is stored on the plate: Restore plate or a restart brings back its files.",
            checkable=True,
        )
        self.action_live_preview.toggled.connect(self._on_live_preview_toggled)
        self.action_clear = create(
            parent,
            "Clear page",
            "eraser",
            self._on_clear_page_clicked,
            tooltip="Remove all objects of the page from the plate, until Restore plate or Live preview fills it again",
        )
        self.action_restore_plate = create(
            parent,
            "Restore plate",
            "backup-restore",
            self._on_restore_plate_clicked,
            tooltip="Show what the files on the plate define, like after a restart.\n" + RESTORE_PLATE_HINT,
        )

        self.set_view(view)

    @property
    def live(self) -> bool:
        """Whether Live preview is on."""
        return self.action_live_preview.isChecked()

    @property
    def view(self) -> Optional["PageLayoutEditorWidget"]:
        """The editor whose page is sent, None without one."""
        return self._view

    def set_view(self, view: Optional["PageLayoutEditorWidget"]):
        """
        Send the page of another editor of the device (e.g. its tab became the active one), None for none. With Live preview
        the plate shows its page right away.
        """
        if view is self._view:
            return
        self._view = view
        self.view_changed(view)
        if self.live and self._device() is not None:
            self.show_page(view.current_index, view)

    def view_changed(self, view: "PageLayoutEditorWidget"):
        """An editor shows another draft, or none: the link follows it, if it is its view."""
        if view is not self._view:
            return
        self.set_session(None if view is None else view.session)
        self.update_actions()

    def update_actions(self):
        view = self._view
        has_data = view is not None and view.session is not None
        busy = has_data and view.busy.busy
        self.action_live_preview.setEnabled(has_data)
        # while Live preview is on, the page on the plate follows the draft
        self.action_clear.setEnabled(has_data and not busy and not self.live)
        self.action_restore_plate.setEnabled(has_data and not busy)

    def _device(self) -> Optional[Device]:
        """The device of the view, None without one."""
        view = self._view
        return None if view is None or view.session is None else view.device_pages_data.device

    def _page_objects(self, index: int) -> List[Dict]:
        """The objects of the draft of the view shown on a page (also those of page 0)."""
        return get_page_objects(self._view.working_objects, index=index, include_global=True)

    def _current_page(self) -> int:
        return self._view.current_index

    @property
    def _dialog_parent(self) -> QWidget:
        return self._parent if self._view is None else self._view

    # --- Live preview ---

    def set_session(self, session: Optional[PlateSession]):
        """Follow the changes of a draft (of the pages of the device, or of a part on its own), None for none."""
        if self._session is session:
            return
        if self._session is not None:
            self._session.remove_listener(self._on_draft_changed)
        self._session = session
        if session is not None:
            session.add_listener(self._on_draft_changed)

    def set_live_guard(self, guard: Callable[[], Optional[str]]):
        """:param guard: says why Live preview can't be turned on now (e.g. too many devices have it on), None if it can"""
        self._live_guard = guard

    def _on_draft_changed(self, _change: DraftChange):
        self.draft_changed()

    def stop_live_preview(self):
        """Turn Live preview off without offering to restore the plate, e.g. when another device is selected."""
        self._stopping_silently = True
        try:
            self.action_live_preview.setChecked(False)
        finally:
            self._stopping_silently = False

    def show_page(self, index: int, view: "PageLayoutEditorWidget"):
        """With Live preview: an editor shows another page, show it on the plate with the objects of the draft if it is the view."""
        # page 0 is no page of the plate: its objects are on all pages
        if self.live and index != 0 and view is self._view:
            self._show_live_page(index)

    def forget_sent(self):
        """
        The plate may no longer show what Live preview sent (e.g. it restarted): send the pages in full again when they are
        shown next.
        """
        self._live_plate = LivePlate()

    def draft_changed(self):
        """With Live preview: send what changed in the draft, soon (changes in a row are sent together)."""
        if self.live:
            self._live_throttle.push(None)

    @qBridge(bool)
    def _on_live_preview_toggled(self, enabled: bool):
        refusal = self._live_guard() if enabled else None
        if refusal is not None:
            self.action_live_preview.blockSignals(True)
            self.action_live_preview.setChecked(False)
            self.action_live_preview.blockSignals(False)
            QMessageBox.information(self._dialog_parent, "Live preview", refusal)
            return
        self.liveChanged.emit(enabled)
        if self._device() is None:
            return
        if enabled:
            self.forget_sent()
            self._show_live_page(self._current_page())
            return
        self._live_throttle.cancel()
        if self._stopping_silently:
            return

        box = QMessageBox(
            QMessageBox.Icon.Question,
            "Live preview off",
            f"{self._device().name} still shows the draft of the editor.\n\n"
            f"Restore the plate, to show what its files define, like after a restart? {RESTORE_PLATE_HINT}",
            parent=self._dialog_parent,
        )
        restore = box.addButton("Restore plate", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Keep the draft", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(restore)
        box.exec()
        if box.clickedButton() is restore:
            self.restore_plate()

    def _show_live_page(self, index: int):
        """Show a page of the draft on the plate: send what it doesn't have of it yet (all of it, the first time)."""
        device = self._device()
        self._live_index = index
        # the editor changes the objects in place, while they are being sent
        objects = copy.deepcopy(self._page_objects(index))
        client = OpenHaspClient(device)
        status = self._status
        description = f"Sending page {index} to {device.name}"
        view = self._view
        view.error_banner.hide()

        async def __async_work():
            async with self._send_lock:
                if self._live_index != index:
                    # the editor went on to another page meanwhile
                    return False
                await self._send_live_update(client, index, objects, status)
                await client.set_page(index)
                return True

        run_busy(
            __async_work(),
            busy=view.busy,
            status=status,
            description=description,
            success_message=f"{device.name} shows page {index} of the draft",
            on_success=lambda shown: self.pageDeployed.emit(index) if shown else None,
            on_error=lambda ex: self._on_send_failed(view, index, description, ex, retry=lambda: view.resync_page(index)),
        )

    def _send_live_changes(self):
        """Send what changed in the draft since the page was last sent."""
        device = self._device()
        if device is None or not self.live:
            return
        index = self._current_page()
        objects = copy.deepcopy(self._page_objects(index))
        client = OpenHaspClient(device)
        description = f"Sending the changes of page {index} to {device.name}"
        view = self._view

        async def __async_work():
            async with self._send_lock:
                if self._live_index != index:
                    # sent when the page is shown again
                    return
                await self._send_live_update(client, index, objects, status=None)

        # not run_busy: disabling the editor would interrupt dragging
        run_async(
            __async_work(),
            on_error=lambda ex: self._on_send_failed(view, index, description, ex, retry=lambda: view.resync_page(index)),
        )

    async def _send_live_update(
        self, client: OpenHaspClient, index: int, objects: List[Dict], status: Optional[OperationStatus]
    ):
        """
        Send what the plate doesn't have of the objects of a page yet. Runs under `_send_lock`.
        :param objects: the objects of the page, including the global ones of page 0
        :param status: reports the progress of a page that is sent in full
        """
        live_plate = self._live_plate
        try:
            update = live_plate.update(index, objects)
            if update is None:
                return
            if update.resend_page:
                await self._send_page(client, index, objects, status)
                live_plate.reset(index, objects)
                return
            await self._send_changes(client, update)
        except BaseException:
            # it is not known what arrived
            self.forget_sent()
            raise

    @staticmethod
    async def _send_changes(client: OpenHaspClient, update: LiveUpdate):
        for page, obj_id in update.deletions:
            await client.delete_object_id(page, obj_id)
        for obj in update.objects:
            await client.jsonl(obj)

    @staticmethod
    async def _send_page(client: OpenHaspClient, index: int, objects: List[Dict], status: Optional[OperationStatus]):
        """Clear the page on the plate and send the given objects (including the global ones of page 0)."""
        await client.clear_page(index)
        for sent, obj in enumerate(objects, start=1):
            await client.jsonl(obj)
            if status is not None:
                status.report_progress(sent, len(objects))
            await asyncio.sleep(SEND_DELAY_SECONDS)

    # --- Clear page, Restore plate ---

    @qBridge()
    def _on_clear_page_clicked(self):
        index = self._current_page()
        answer = QMessageBox.question(
            self._dialog_parent,
            "Clear page",
            f"Clear page {index} on {self._device().name}?\n\nThis removes all objects of the page from the plate, "
            f"until Restore plate or Live preview fills it again. The draft in the editor is not changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._clear_page(index)

    def _clear_page(self, index: int):
        device = self._device()
        client = OpenHaspClient(device)
        description = f"Clearing page {index} on {device.name}"
        view = self._view
        view.error_banner.hide()
        run_busy(
            client.clear_page(index),
            busy=view.busy,
            status=self._status,
            description=description,
            success_message=f"Cleared page {index} on {device.name}",
            # the page on the plate is empty now, its files are not
            on_success=lambda _: self.pageOutOfSync.emit(index),
            on_error=lambda ex: self._on_send_failed(view, index, description, ex, retry=lambda: self._clear_page(index)),
        )

    @qBridge()
    def _on_restore_plate_clicked(self):
        answer = QMessageBox.question(
            self._dialog_parent,
            "Restore plate",
            f"Restore {self._device().name}?\n\nAll pages are cleared and built again from the files on the plate, "
            f"like after a restart. {RESTORE_PLATE_HINT}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restore_plate()

    def restore_plate(self):
        """Rebuild all pages of the plate from its own files, like after a restart (Live preview ends)."""
        self.stop_live_preview()
        device = self._device()
        client = OpenHaspClient(device)
        description = f"Restoring {device.name} from its files"
        view = self._view
        view.error_banner.hide()

        async def __async_work():
            async with self._send_lock:
                await client.restore_from_files()
                self.forget_sent()

        run_busy(
            __async_work(),
            busy=view.busy,
            status=self._status,
            description=description,
            success_message=f"{device.name} shows its files again",
            on_success=lambda _: self.plateRestored.emit(),
            on_error=lambda ex: view.error_banner.show_error(f"{description} failed: {error_text(ex)}", retry=self.restore_plate),
        )

    def _on_send_failed(
        self, view: "PageLayoutEditorWidget", index: int, description: str, ex: Exception, retry: Callable[[], None]
    ):
        """:param view: the editor whose page was sent: it shows the error"""
        self.pageOutOfSync.emit(index)
        view.error_banner.show_error(f"{description} failed: {error_text(ex)}", retry=retry)
