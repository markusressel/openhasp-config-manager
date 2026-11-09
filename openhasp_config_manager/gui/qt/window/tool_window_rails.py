"""
The tool windows of the main window (see `gui/domain/tool_window_rails.py`): the docks around the preview, arranged in the
places (`Slot`) of a `ToolWindowLayout`, and a rail with their buttons at the left, right and bottom edge. Every dock of
the window gets a button, also docks added later: the rails find them themselves. A dock without the closable feature
(the preview) has none, and `describe_dock` sets the icon of a dock, its first place, whether it is open at first, or
that it has no button.

The layout is the only arrangement of the docks: they are built from it (`apply_layout`), and can't be dragged to other
places with their title bars, only with their buttons (or their context menu). Whether a dock is open is the dock's own
state, whichever way it is opened or closed (its button, the View menu, its close button, code): the rails follow its
`toggleViewAction`, and close the other dock of its place when it opens.
"""

import json
import logging
import weakref
from typing import Dict, List, Optional

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QMimeData, QObject, QPoint, QRect, QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QDrag, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QBoxLayout,
    QDockWidget,
    QMainWindow,
    QMenu,
    QSizePolicy,
    QToolBar,
    QWidget,
)

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.tool_window_rails import (
    RailClick,
    Side,
    Slot,
    ToolWindowLayout,
    click_action,
    drop_target,
)
from openhasp_config_manager.gui.qt.components import ThemedIcons

LOGGER = logging.getLogger(__name__)

# dynamic properties of a dock, set by `describe_dock`
ICON_PROPERTY = "railIcon"
SLOT_PROPERTY = "railSlot"
OPEN_PROPERTY = "railOpen"
BUTTON_PROPERTY = "railButton"

LAYOUT_KEY = "window/tool_windows"
SHOW_RAILS_KEY = "window/show_rails"
# what a dragged button carries: the object name of its dock
MIME_TYPE = "application/x-openhasp-config-manager-tool-window"

DEFAULT_ICON = "dock-window"
# the place of a dock that wasn't described
DEFAULT_SLOT = Slot.BOTTOM_LEFT
# the size of a place across the window while it has none remembered: the width of a column, the height of the bottom
DEFAULT_SIZES = {Side.LEFT: 280, Side.RIGHT: 360, Side.BOTTOM: 280}

_TOOLBAR_AREAS = {
    Side.LEFT: Qt.ToolBarArea.LeftToolBarArea,
    Side.RIGHT: Qt.ToolBarArea.RightToolBarArea,
    Side.BOTTOM: Qt.ToolBarArea.BottomToolBarArea,
}


def describe_dock(
    dock: QDockWidget, icon: Optional[str] = None, slot: Optional[Slot] = None, is_open: bool = False, button: bool = True
):
    """
    How a dock shows on the rails. A dock that isn't described gets a button with a generic icon, at the bottom left.

    :param icon: the mdi6 icon of its button
    :param slot: its place, until the user moves it
    :param is_open: open at the first start (and after "Restore default layout")
    :param button: False for a dock without a button
    """
    if icon is not None:
        dock.setProperty(ICON_PROPERTY, icon)
    if slot is not None:
        dock.setProperty(SLOT_PROPERTY, slot.value)
    dock.setProperty(OPEN_PROPERTY, is_open)
    dock.setProperty(BUTTON_PROPERTY, button)


class RailButton(QAbstractButton):
    """The button of a dock: its icon and title, turned along the rail like in IntelliJ (bottom to top on the left)."""

    ICON_SIZE = 16
    PADDING_ALONG = UiDimensions.one
    PADDING_ACROSS = UiDimensions.half // 2 + 1
    GAP = UiDimensions.half

    def __init__(self, dock: QDockWidget, rails: "ToolWindowRails"):
        super().__init__()
        self.dock = dock
        self.side = Side.LEFT
        # weak: a cycle of the rails and their buttons would let the garbage collector clear the rails before Qt deletes
        # the window, whose events they still filter then
        self._rails = weakref.ref(rails)
        self._press: Optional[QPoint] = None
        self.setCheckable(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setText(dock.windowTitle())
        ThemedIcons.apply(self, dock.property(ICON_PROPERTY) or DEFAULT_ICON)
        action = dock.toggleViewAction()
        self.setChecked(action.isChecked())
        action.toggled.connect(self.setChecked)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        rails = self._rails()
        if rails is not None:
            rails.toggle(self.dock)

    def nextCheckState(self):
        # a click doesn't check the button: the dock does, when it is shown or hidden
        pass

    def setText(self, text: str):
        super().setText(text)
        self.setToolTip(f"{text}\nDrag to another group or rail to move it, right-click for more")
        self.updateGeometry()

    def set_side(self, side: Side):
        if side != self.side:
            self.side = side
            self.updateGeometry()
            self.update()

    # --- dragging to another place ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._press is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()
        ):
            self._press = None
            # not a click anymore
            self.setDown(False)
            drag = QDrag(self)
            data = QMimeData()
            data.setData(MIME_TYPE, self.dock.objectName().encode())
            drag.setMimeData(data)
            drag.setPixmap(self.grab())
            drag.setHotSpot(event.position().toPoint())
            drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        rails = self._rails()
        if rails is not None:
            rails.menu(self.dock).exec(event.globalPos())

    # --- painting ---

    def _content_size(self) -> QSize:
        """The size of icon and text, as they are drawn on a horizontal rail."""
        metrics = self.fontMetrics()
        width = self.ICON_SIZE + self.GAP + metrics.horizontalAdvance(self.text())
        height = max(self.ICON_SIZE, metrics.height())
        return QSize(width + 2 * self.PADDING_ALONG, height + 2 * self.PADDING_ACROSS)

    def sizeHint(self) -> QSize:
        size = self._content_size()
        return size.transposed() if self.side.vertical else size

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.palette().color(QPalette.ColorRole.WindowText)

        alpha = 70 if self.isChecked() else 0
        if self.underMouse():
            alpha += 22
        if alpha:
            background = QColor(text)
            background.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), UiDimensions.half, UiDimensions.half)

        # the icon stays upright, at the start of the text: the bottom on the left rail, the top on the right one
        width, height = self.width(), self.height()
        icon = self.ICON_SIZE
        if self.side == Side.LEFT:
            icon_rect = QRect((width - icon) // 2, height - self.PADDING_ALONG - icon, icon, icon)
        elif self.side == Side.RIGHT:
            icon_rect = QRect((width - icon) // 2, self.PADDING_ALONG, icon, icon)
        else:
            icon_rect = QRect(self.PADDING_ALONG, (height - icon) // 2, icon, icon)
        self.icon().paint(painter, icon_rect, mode=QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled)

        # the text, drawn horizontally in a turned painter
        painter.save()
        if self.side == Side.LEFT:
            painter.translate(0, height)
            painter.rotate(-90)
            length, thickness = height, width
        elif self.side == Side.RIGHT:
            painter.translate(width, 0)
            painter.rotate(90)
            length, thickness = height, width
        else:
            length, thickness = width, height
        start = self.PADDING_ALONG + icon + self.GAP
        if not self.isChecked():
            text.setAlpha(190)
        painter.setPen(text)
        painter.drawText(
            QRect(start, 0, length - start, thickness),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )
        painter.restore()


class RailContainer(QWidget):
    """The buttons of a rail: the group of the place at its start, a gap, the group of the place at its end. Takes drops."""

    def __init__(self, side: Side, rails: "ToolWindowRails"):
        super().__init__()
        self.side = side
        # weak, like the buttons
        self._rails = weakref.ref(rails)
        # where a dragged button would go, along the rail; None while nothing is dragged over it
        self._indicator: Optional[int] = None
        direction = QBoxLayout.Direction.TopToBottom if side.vertical else QBoxLayout.Direction.LeftToRight
        layout = QBoxLayout(direction, self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.groups: Dict[bool, QBoxLayout] = {}
        for secondary in (False, True):
            if secondary:
                layout.addStretch(1)
            group = QBoxLayout(direction)
            group.setContentsMargins(0, 0, 0, 0)
            group.setSpacing(UiDimensions.half // 2)
            layout.addLayout(group)
            self.groups[secondary] = group
        if side.vertical:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAcceptDrops(True)

    def buttons(self, secondary: bool) -> List[RailButton]:
        group = self.groups[secondary]
        return [group.itemAt(index).widget() for index in range(group.count())]

    def set_buttons(self, secondary: bool, buttons: List[RailButton]):
        if buttons == self.buttons(secondary):
            return
        group = self.groups[secondary]
        for button in self.buttons(secondary):
            group.removeWidget(button)
        for button in buttons:
            button.set_side(self.side)
            group.addWidget(button)

    def _along(self, point: QPoint) -> int:
        return point.y() if self.side.vertical else point.x()

    def target(self, point: QPoint):
        """:return: the place and index a button dropped at a point goes to"""
        length = self.height() if self.side.vertical else self.width()

        def centers(secondary: bool) -> List[int]:
            return [self._along(button.geometry().center()) for button in self.buttons(secondary)]

        return drop_target(self.side, length, self._along(point), centers(False), centers(True))

    @staticmethod
    def _accepts(event) -> bool:
        return event.mimeData().hasFormat(MIME_TYPE)

    def dragEnterEvent(self, event):
        if self._accepts(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not self._accepts(event):
            return
        event.acceptProposedAction()
        slot, index = self.target(event.position().toPoint())
        buttons = self.buttons(slot.secondary)
        if index < len(buttons):
            geometry = buttons[index].geometry()
            self._indicator = self._along(geometry.topLeft())
        elif buttons:
            geometry = buttons[-1].geometry()
            self._indicator = self._along(geometry.bottomRight()) + 1
        else:
            # an empty group: at its end of the rail
            length = self.height() if self.side.vertical else self.width()
            self._indicator = length - 2 if slot.secondary else 1
        self.update()

    def dragLeaveEvent(self, event):
        self._indicator = None
        self.update()

    def dropEvent(self, event):
        self._indicator = None
        self.update()
        if not self._accepts(event):
            return
        event.acceptProposedAction()
        slot, index = self.target(event.position().toPoint())
        rails = self._rails()
        if rails is not None:
            rails.move(bytes(event.mimeData().data(MIME_TYPE)).decode(), slot, index)

    def paintEvent(self, event):
        if self._indicator is None:
            return
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().color(QPalette.ColorRole.Highlight))
        if self.side.vertical:
            painter.drawRect(QRect(1, self._indicator - 1, self.width() - 2, 3))
        else:
            painter.drawRect(QRect(self._indicator - 1, 1, 3, self.height() - 2))


class ToolWindowRails(QObject):
    """The tool windows of a main window and their rails (see the module)."""

    def __init__(self, window: QMainWindow, center: QDockWidget):
        """
        :param center: the dock the others are placed around (the preview), in the window's left dock area
        """
        super().__init__(window)
        # weak: the window keeps the rails (`window.rails`), a cycle would let the garbage collector clear the rails before
        # Qt deletes the window, whose events they still filter then
        self._window_ref = weakref.ref(window)
        # the minimum size of the window without the rails
        self._base_minimum = window.minimumSize()
        self._center = center
        self._buttons: Dict[QDockWidget, RailButton] = {}
        self._docks: Dict[str, QDockWidget] = {}
        # the dock of each toggle view action, for its signal
        self._actions: Dict[QAction, QDockWidget] = {}
        # while the docks are rebuilt: their hiding and showing is not the user's
        self._building = False
        self._sized = False

        self.layout = ToolWindowLayout()
        self._load_layout()

        self.action_show_rails = QAction("Tool window bars", self)
        self.action_show_rails.setCheckable(True)
        self.action_show_rails.setToolTip("Show a button for each panel at the edges of the window")
        self.action_show_rails.setChecked(QSettings().value(SHOW_RAILS_KEY, True, type=bool))
        self.action_show_rails.toggled.connect(self._on_show_rails_toggled)

        # docks added or removed later rebuild the layout once
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(0)
        self._update_timer.timeout.connect(self._on_children_changed)

        self._rails: Dict[Side, QToolBar] = {}
        self._containers: Dict[Side, RailContainer] = {}
        for side in Side:
            self._create_rail(side)

        self._find_docks()
        self.layout.normalize()
        self.apply_layout()
        window.installEventFilter(self)

    @property
    def _window(self) -> QMainWindow:
        return self._window_ref()

    def _create_rail(self, side: Side):
        rail = QToolBar(f"{side.value.capitalize()} tool window bar", self._window)
        rail.setObjectName(f"rail_{side.value}")
        rail.setProperty("role", "rail")
        rail.setMovable(False)
        rail.setFloatable(False)
        rail.setAllowedAreas(_TOOLBAR_AREAS[side])
        # shown and hidden with the View menu action, not one of its own
        rail.toggleViewAction().setVisible(False)
        container = RailContainer(side, self)
        rail.addWidget(container)
        self._window.addToolBar(_TOOLBAR_AREAS[side], rail)
        rail.hide()
        self._rails[side] = rail
        self._containers[side] = container

    # --- queries ---

    def button(self, dock: QDockWidget) -> Optional[RailButton]:
        return self._buttons.get(dock)

    def rail(self, side: Side) -> QToolBar:
        return self._rails[side]

    def container(self, side: Side) -> RailContainer:
        return self._containers[side]

    def buttons(self, side: Side) -> List[RailButton]:
        """The buttons of a rail, in their order: those of the group at its start, then those at its end."""
        container = self._containers[side]
        return container.buttons(False) + container.buttons(True)

    def side_of(self, dock: QDockWidget) -> Optional[Side]:
        """The rail of the button of a dock, None without one."""
        slot = self.slot_of(dock)
        return None if slot is None else slot.side

    def slot_of(self, dock: QDockWidget) -> Optional[Slot]:
        return self.layout.slot_of(dock.objectName()) if dock in self._buttons else None

    def dock(self, name: str) -> QDockWidget:
        return self._docks[name]

    # --- actions ---

    def toggle(self, dock: QDockWidget):
        """What a click on the button of a dock does: open it (closing the other one of its place) or close it."""
        if click_action(dock.toggleViewAction().isChecked()) is RailClick.HIDE:
            dock.hide()
        else:
            dock.show()
            dock.raise_()

    def move(self, name: str, slot: Slot, index: Optional[int] = None):
        """Move a dock to a place (see `ToolWindowLayout.move`), and rebuild the docks if it changed its place."""
        if name not in self._docks:
            return
        dock = self._docks[name]
        if dock.isFloating():
            dock.setFloating(False)
        self._remember_sizes()
        if self.layout.move(name, slot, index):
            self.apply_layout()
        else:
            self._update_buttons()

    def menu(self, dock: QDockWidget) -> QMenu:
        """The context menu of the button of a dock."""
        menu = QMenu(self._window)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        name = dock.objectName()
        is_open = dock.toggleViewAction().isChecked()
        menu.addAction("Close" if is_open else "Open", lambda: self.toggle(dock))
        move_to = menu.addMenu("Move to")
        current = self.layout.slot_of(name)
        for slot in Slot:
            action = move_to.addAction(slot.label, lambda slot=slot: self.move(name, slot))
            action.setCheckable(True)
            action.setChecked(slot == current)
            action.setEnabled(slot != current)
        if dock.features() & QDockWidget.DockWidgetFeature.DockWidgetFloatable:
            floating = menu.addAction("Floating window", lambda: self._set_floating(dock, not dock.isFloating()))
            floating.setCheckable(True)
            floating.setChecked(dock.isFloating())
        return menu

    def _set_floating(self, dock: QDockWidget, floating: bool):
        if floating and not dock.toggleViewAction().isChecked():
            dock.show()
        dock.setFloating(floating)

    def reset(self):
        """Every dock back to its first place, open if it was at first, in its first size."""
        for dock in self._docks.values():
            if dock.isFloating():
                dock.setFloating(False)
        self.layout.reset()
        self.apply_layout()

    # --- building the docks ---

    def apply_layout(self):
        """Arrange the docks as the layout says: the places around the preview, the open dock of each place shown."""
        self._building = True
        try:
            docks = {slot: [self._docks[name] for name in self.layout.views(slot)] for slot in Slot}
            docked = {slot: [dock for dock in members if not dock.isFloating()] for slot, members in docks.items()}
            for members in docked.values():
                for dock in members:
                    self._window.removeDockWidget(dock)
            first = {slot: members[0] for slot, members in docked.items() if members}
            horizontal, vertical = Qt.Orientation.Horizontal, Qt.Orientation.Vertical
            window, center = self._window, self._center
            left = first.get(Slot.LEFT_TOP) or first.get(Slot.LEFT_BOTTOM)
            if left is not None:
                window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left)
                window.splitDockWidget(left, center, horizontal)
                if Slot.LEFT_TOP in first and Slot.LEFT_BOTTOM in first:
                    window.splitDockWidget(first[Slot.LEFT_TOP], first[Slot.LEFT_BOTTOM], vertical)
            right = first.get(Slot.RIGHT_TOP) or first.get(Slot.RIGHT_BOTTOM)
            if right is not None:
                window.splitDockWidget(center, right, horizontal)
                if Slot.RIGHT_TOP in first and Slot.RIGHT_BOTTOM in first:
                    window.splitDockWidget(first[Slot.RIGHT_TOP], first[Slot.RIGHT_BOTTOM], vertical)
            bottom = first.get(Slot.BOTTOM_LEFT) or first.get(Slot.BOTTOM_RIGHT)
            if bottom is not None:
                window.splitDockWidget(center, bottom, vertical)
                if Slot.BOTTOM_LEFT in first and Slot.BOTTOM_RIGHT in first:
                    window.splitDockWidget(first[Slot.BOTTOM_LEFT], first[Slot.BOTTOM_RIGHT], horizontal)
            # the other docks of a place share it: only one of them is open
            for slot, members in docked.items():
                for dock in members[1:]:
                    window.tabifyDockWidget(members[0], dock)
            for members in docked.values():
                for dock in members:
                    dock.setVisible(dock.objectName() in self.layout.open)
        finally:
            self._building = False
        self._update_buttons()
        if self._window.isVisible():
            self.apply_sizes()

    def apply_sizes(self):
        """The size of each place that shows a dock: the remembered one, else the default."""
        self._update_minimum_size()
        shown = {
            slot: self._docks[name]
            for slot in Slot
            if (name := self.layout.shown(slot)) is not None and not self._docks[name].isFloating()
        }

        def size(slot: Slot, index: int) -> int:
            remembered = self.layout.sizes.get(slot)
            if remembered is not None:
                return remembered[index]
            return DEFAULT_SIZES[slot.side]

        columns, widths = [], []
        for side in (Side.LEFT, Side.RIGHT):
            slot = next((slot for slot in Slot if slot.side == side and slot in shown), None)
            if slot is not None:
                columns.append(shown[slot])
                widths.append(size(slot, 0))
        if columns:
            self._window.resizeDocks(columns, widths, Qt.Orientation.Horizontal)
        bottom = next((slot for slot in (Slot.BOTTOM_LEFT, Slot.BOTTOM_RIGHT) if slot in shown), None)
        if bottom is not None:
            self._window.resizeDocks([shown[bottom]], [size(bottom, 1)], Qt.Orientation.Vertical)
        # the two places of a side, where both show a dock: as remembered, else in halves
        for primary, orientation, index in (
            (Slot.LEFT_TOP, Qt.Orientation.Vertical, 1),
            (Slot.RIGHT_TOP, Qt.Orientation.Vertical, 1),
            (Slot.BOTTOM_LEFT, Qt.Orientation.Horizontal, 0),
        ):
            secondary = primary.partner()
            if primary not in shown or secondary not in shown:
                continue
            docks = [shown[primary], shown[secondary]]
            if primary in self.layout.sizes and secondary in self.layout.sizes:
                lengths = [self.layout.sizes[primary][index], self.layout.sizes[secondary][index]]
            else:
                total = sum(dock.height() if orientation == Qt.Orientation.Vertical else dock.width() for dock in docks)
                lengths = [total // 2, total - total // 2]
            self._window.resizeDocks(docks, lengths, orientation)
        self._sized = True

    def _remember_sizes(self, skip: Optional[Slot] = None):
        """
        The sizes of the places that show a dock now, so they keep them when the docks are rebuilt or the app restarts.

        :param skip: a place whose dock just opened: it doesn't have its size yet
        """
        if not self._window.isVisible():
            return
        for slot in Slot:
            name = self.layout.shown(slot)
            if name is not None and slot != skip:
                self._remember_size(slot, self._docks[name])

    def _remember_size(self, slot: Slot, dock: QDockWidget):
        # also of a dock that was just closed: its geometry is the last one it had
        if not dock.isFloating() and dock.width() > 0 and dock.height() > 0:
            self.layout.sizes[slot] = (dock.width(), dock.height())

    # --- the docks ---

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self.__dict__:
            # the garbage collector cleared the rails of a window that is gone, before Qt deleted it: the events of its
            # deletion still come here
            return False
        kind = event.type()
        if watched is self._window:
            if kind in (QEvent.Type.ChildAdded, QEvent.Type.ChildRemoved):
                # a dock may have been added or removed
                self._update_timer.start()
            elif kind == QEvent.Type.Show and not self._sized:
                # the sizes need the window's size
                QTimer.singleShot(0, self.apply_sizes)
        elif isinstance(watched, QDockWidget):
            if kind == QEvent.Type.WindowTitleChange and watched in self._buttons:
                self._buttons[watched].setText(watched.windowTitle())
        return False

    def _on_children_changed(self):
        if self._find_docks():
            self._remember_sizes()
            self.apply_layout()

    def _find_docks(self) -> bool:
        """:return: whether a dock was added or removed"""
        changed = False
        for dock in list(self._buttons):
            if sip.isdeleted(dock) or dock.parent() is not self._window:
                self._remove(dock)
                changed = True
        for dock in self._window.findChildren(QDockWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if dock not in self._buttons and self._has_button(dock):
                self._add(dock)
                changed = True
        return changed

    @staticmethod
    def _has_button(dock: QDockWidget) -> bool:
        if dock.property(BUTTON_PROPERTY) is False:
            return False
        # a dock that can't be closed is always there: it needs no button
        return bool(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetClosable)

    def _add(self, dock: QDockWidget):
        name = dock.objectName()
        slot = dock.property(SLOT_PROPERTY)
        self.layout.add(name, Slot(slot) if slot is not None else DEFAULT_SLOT, bool(dock.property(OPEN_PROPERTY)))
        self._docks[name] = dock
        # dragged with its button, not its title bar: the layout is the only arrangement
        dock.setFeatures(dock.features() & ~QDockWidget.DockWidgetFeature.DockWidgetMovable)
        button = RailButton(dock, self)
        self._buttons[dock] = button
        dock.installEventFilter(self)
        # bound methods, no lambdas: Qt would keep the rails alive in a cycle with the docks (see `RailButton`)
        action = dock.toggleViewAction()
        self._actions[action] = dock
        action.toggled.connect(self._on_toggled)
        dock.topLevelChanged.connect(self._on_top_level_changed)

    def _remove(self, dock: QDockWidget):
        button = self._buttons.pop(dock)
        name = next(name for name, known in self._docks.items() if known is dock)
        del self._docks[name]
        self._actions = {action: known for action, known in self._actions.items() if known is not dock}
        self.layout.remove(name)
        if not sip.isdeleted(button):
            button.setParent(None)
            button.deleteLater()

    def _on_toggled(self, checked: bool):
        dock = self._actions.get(self.sender())
        if self._building or dock is None:
            return
        name = dock.objectName()
        slot = self.layout.slot_of(name)
        visible = self._window.isVisible()
        if checked and not dock.isFloating():
            if visible:
                self._remember_sizes(skip=slot)
            # one dock per place: the one that was open there closes, and leaves its size to it
            for other in self.layout.others_open(name):
                if not self._docks[other].isFloating():
                    if visible and self._docks[other].isVisible():
                        self._remember_size(slot, self._docks[other])
                    self._docks[other].hide()
            if visible:
                # the place gets its size once Qt placed the dock
                QTimer.singleShot(0, self.apply_sizes)
        elif not checked and visible and self.layout.shown(slot) == name:
            self._remember_size(slot, dock)
        self.layout.set_open(name, checked)

    def _on_top_level_changed(self, floating: bool):
        dock = self.sender()
        if self._building or floating or dock not in self._buttons:
            return
        # docked again: back in its place, as the only open dock there
        if dock.toggleViewAction().isChecked():
            for other in self.layout.others_open(dock.objectName()):
                if not self._docks[other].isFloating():
                    self.layout.set_open(other, False)
        self._remember_sizes()
        QTimer.singleShot(0, self.apply_layout)

    # --- the rails ---

    def _update_buttons(self):
        for side in Side:
            container = self._containers[side]
            for secondary in (False, True):
                slot = Slot.of(side, secondary)
                container.set_buttons(secondary, [self._buttons[self._docks[name]] for name in self.layout.views(slot)])
            rail = self._rails[side]
            visible = bool(self.buttons(side)) and self.action_show_rails.isChecked()
            if rail.isHidden() == visible:
                rail.setVisible(visible)
        self._update_minimum_size()

    def _update_minimum_size(self):
        """
        The minimum size of the window is that of its docks: the rails need room of their own, and the open docks next
        to each other theirs (else they would overlap).
        """
        width = sum(
            self._rails[side].sizeHint().width() for side in (Side.LEFT, Side.RIGHT) if not self._rails[side].isHidden()
        )
        height = self._rails[Side.BOTTOM].sizeHint().height() if not self._rails[Side.BOTTOM].isHidden() else 0
        needed = self._window.layout().minimumSize()
        self._window.setMinimumSize(
            max(self._base_minimum.width() + width, needed.width()), max(self._base_minimum.height() + height, needed.height())
        )

    # --- settings ---

    def _on_show_rails_toggled(self, shown: bool):
        QSettings().setValue(SHOW_RAILS_KEY, shown)
        self._update_buttons()

    def _load_layout(self):
        try:
            value = json.loads(QSettings().value(LAYOUT_KEY, "null"))
        except (TypeError, ValueError):
            value = None
        if value is not None and not self.layout.load(value):
            LOGGER.warning("Ignoring the remembered arrangement of the panels: it can't be read")

    def save(self):
        """Remember the arrangement, the open docks and the sizes of the places."""
        self._remember_sizes()
        QSettings().setValue(LAYOUT_KEY, json.dumps(self.layout.to_json()))
