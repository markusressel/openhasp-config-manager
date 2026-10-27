import asyncio
import copy
from typing import Callable, Dict, List, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QMessageBox, QWidget

from openhasp_config_manager.gui.domain.live_preview import LivePage
from openhasp_config_manager.gui.qt.async_bridge import qBridge, run_async
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.operations import BusyState, OperationStatus, error_text, run_busy
from openhasp_config_manager.gui.qt.throttle import LatestValueThrottle
from openhasp_config_manager.gui.qt.widgets.message_panel import ErrorBanner
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

# delay between two objects when sending a whole page, to avoid overwhelming the device
SEND_DELAY_SECONDS = 0.1
# Live preview sends the changes of the draft at most this often, e.g. while dragging an object
LIVE_PREVIEW_INTERVAL_MS = 50

RESTORE_PLATE_HINT = "Values sent by haad or Home Assistant appear again with their next update."


class PlateLink(QtCore.QObject):
    """
    What the editor does on the plate of its device: *Live preview* (the draft on the plate while editing), *Clear page* and
    *Restore plate*, with their actions. Everything is sent in order: a page that is sent in full, then the changes after it.
    """

    # a page on the device may differ from what it should show: sending it failed, or it was cleared
    pageOutOfSync = QtCore.pyqtSignal(int)
    # the plate shows the page of the draft
    pageDeployed = QtCore.pyqtSignal(int)
    # the plate shows its files again
    plateRestored = QtCore.pyqtSignal()
    # Live preview was turned on or off
    liveChanged = QtCore.pyqtSignal(bool)

    def __init__(
        self,
        parent: QWidget,
        status: OperationStatus,
        busy: BusyState,
        error_banner: ErrorBanner,
        device: Callable[[], Optional[Device]],
        page_objects: Callable[[int], List[Dict]],
        current_page: Callable[[], int],
        resync: Callable[[int], None],
    ):
        """
        :param parent: the editor, also the parent of the questions asked
        :param device: the device of the editor, None without one
        :param page_objects: the objects of the draft shown on a page (also those of page 0)
        :param current_page: the page the editor shows
        :param resync: brings a page of the plate back to what it should show (see `PageLayoutEditorWidget.resync_page`)
        """
        super().__init__(parent)
        self._parent = parent
        self._status = status
        self._busy = busy
        self._error_banner = error_banner
        self._device = device
        self._page_objects = page_objects
        self._current_page = current_page
        self._resync = resync

        # what the plate shows of the current page, and the changes of the draft that wait to be sent
        self._live_page = LivePage()
        self._live_throttle = LatestValueThrottle(
            lambda _: self._send_live_changes(), interval_ms=LIVE_PREVIEW_INTERVAL_MS, parent=self
        )
        self._stopping_silently = False
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

    @property
    def live(self) -> bool:
        """Whether Live preview is on."""
        return self.action_live_preview.isChecked()

    def update_actions(self, has_data: bool):
        busy = self._busy.busy
        self.action_live_preview.setEnabled(has_data)
        # while Live preview is on, the page on the plate follows the draft
        self.action_clear.setEnabled(has_data and not busy and not self.live)
        self.action_restore_plate.setEnabled(has_data and not busy)

    # --- Live preview ---

    def stop_live_preview(self):
        """Turn Live preview off without offering to restore the plate, e.g. when another device is selected."""
        self._stopping_silently = True
        try:
            self.action_live_preview.setChecked(False)
        finally:
            self._stopping_silently = False

    def show_page(self, index: int):
        """With Live preview: the editor shows another page, show it on the plate with the objects of the draft."""
        # page 0 is no page of the plate: its objects are on all pages
        if self.live and index != 0:
            self._start_live_page(index)

    def draft_changed(self):
        """With Live preview: send what changed in the draft, soon (changes in a row are sent together)."""
        if self.live:
            self._live_throttle.push(None)

    @qBridge(bool)
    def _on_live_preview_toggled(self, enabled: bool):
        self.liveChanged.emit(enabled)
        if self._device() is None:
            return
        if enabled:
            self._start_live_page(self._current_page())
            return
        self._live_throttle.cancel()
        if self._stopping_silently:
            return

        box = QMessageBox(
            QMessageBox.Icon.Question,
            "Live preview off",
            f"{self._device().name} still shows the draft of the editor.\n\n"
            f"Restore the plate, to show what its files define, like after a restart? {RESTORE_PLATE_HINT}",
            parent=self._parent,
        )
        restore = box.addButton("Restore plate", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Keep the draft", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(restore)
        box.exec()
        if box.clickedButton() is restore:
            self.restore_plate()

    def _start_live_page(self, index: int):
        objects = self._page_objects(index)
        self._live_page.reset(objects)
        self._send_page(index, objects, show=True)

    def _send_live_changes(self):
        """Send what changed in the draft since the page was last sent."""
        device = self._device()
        if device is None or not self.live:
            return
        index = self._current_page()
        objects = self._page_objects(index)
        update = self._live_page.update(objects)
        if update is None:
            return
        if update.resend_page:
            self._send_page(index, objects, show=False)
            return

        client = OpenHaspClient(device)
        description = f"Sending the changes of page {index} to {device.name}"

        async def __async_work():
            async with self._send_lock:
                for page, obj_id in update.deletions:
                    await client.delete_object_id(page, obj_id)
                for obj in update.objects:
                    await client.jsonl(obj)

        # not run_busy: disabling the editor would interrupt dragging
        run_async(
            __async_work(),
            on_error=lambda ex: self._on_send_failed(index, description, ex, retry=lambda: self._resync(index)),
        )

    def _send_page(self, index: int, objects: List[Dict], show: bool):
        """
        Clear the page on the plate and send the given objects (including the global ones of page 0).
        :param show: switch the plate to the page afterwards
        """
        device = self._device()
        # the editor changes the objects in place, while they are being sent
        objects = copy.deepcopy(objects)
        client = OpenHaspClient(device)
        status = self._status
        description = f"Sending page {index} to {device.name}"
        self._error_banner.hide()

        async def __async_work():
            async with self._send_lock:
                await client.clear_page(index)
                for sent, obj in enumerate(objects, start=1):
                    await client.jsonl(obj)
                    status.report_progress(sent, len(objects))
                    await asyncio.sleep(SEND_DELAY_SECONDS)
                if show:
                    await client.set_page(index)

        run_busy(
            __async_work(),
            busy=self._busy,
            status=status,
            description=description,
            success_message=f"{device.name} shows page {index} of the draft ({len(objects)} objects)",
            on_success=lambda _: self.pageDeployed.emit(index),
            on_error=lambda ex: self._on_send_failed(index, description, ex, retry=lambda: self._resync(index)),
        )

    # --- Clear page, Restore plate ---

    @qBridge()
    def _on_clear_page_clicked(self):
        index = self._current_page()
        answer = QMessageBox.question(
            self._parent,
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
        self._error_banner.hide()
        run_busy(
            client.clear_page(index),
            busy=self._busy,
            status=self._status,
            description=description,
            success_message=f"Cleared page {index} on {device.name}",
            # the page on the plate is empty now, its files are not
            on_success=lambda _: self.pageOutOfSync.emit(index),
            on_error=lambda ex: self._on_send_failed(index, description, ex, retry=lambda: self._clear_page(index)),
        )

    @qBridge()
    def _on_restore_plate_clicked(self):
        answer = QMessageBox.question(
            self._parent,
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
        self._error_banner.hide()

        async def __async_work():
            async with self._send_lock:
                await client.restore_from_files()

        run_busy(
            __async_work(),
            busy=self._busy,
            status=self._status,
            description=description,
            success_message=f"{device.name} shows its files again",
            on_success=lambda _: self.plateRestored.emit(),
            on_error=lambda ex: self._error_banner.show_error(
                f"{description} failed: {error_text(ex)}", retry=self.restore_plate
            ),
        )

    def _on_send_failed(self, index: int, description: str, ex: Exception, retry: Callable[[], None]):
        self.pageOutOfSync.emit(index)
        self._error_banner.show_error(f"{description} failed: {error_text(ex)}", retry=retry)
