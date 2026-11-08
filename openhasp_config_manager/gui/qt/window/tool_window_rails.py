"""
The tool window rails of the main window (see `gui/domain/tool_window_rails.py`): a strip of buttons at each edge, one
button per dock, on the side where the dock is. Every dock of the window gets one, also docks added later: the rails
find them themselves. A dock without the closable feature (the preview) has none, and `describe_dock` sets the icon of
a dock, the side of its button while it was never seen, or that it has none.

The state of a button is the dock's: it is checked while the dock's `toggleViewAction` is, and shows whether the dock can
be seen or is behind another dock of its tab group. Nothing else is stored, so opening or closing a dock any other way
(the View menu, its close button, restoring the window state, code) shows on its button.
"""

import json
import logging
from typing import Dict, List, Optional, Set

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QRect, QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import QAbstractButton, QBoxLayout, QDockWidget, QMainWindow, QTabBar, QToolBar, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.tool_window_rails import (
    Placement,
    RailClick,
    Rect,
    Side,
    arrange,
    click_action,
    place,
)
from openhasp_config_manager.gui.qt.components import ThemedIcons

LOGGER = logging.getLogger(__name__)

# dynamic properties of a dock, set by `describe_dock`
ICON_PROPERTY = "railIcon"
SIDE_PROPERTY = "railSide"
BUTTON_PROPERTY = "railButton"

# the placements of the buttons, for docks that are hidden at the start
PLACEMENTS_KEY = "window/rail_placements"
SHOW_RAILS_KEY = "window/show_rails"

DEFAULT_ICON = "dock-window"

_AREA_SIDES = {
    Qt.DockWidgetArea.LeftDockWidgetArea: Side.LEFT,
    Qt.DockWidgetArea.RightDockWidgetArea: Side.RIGHT,
    Qt.DockWidgetArea.TopDockWidgetArea: Side.TOP,
    Qt.DockWidgetArea.BottomDockWidgetArea: Side.BOTTOM,
}
_TOOLBAR_AREAS = {
    Side.LEFT: Qt.ToolBarArea.LeftToolBarArea,
    Side.RIGHT: Qt.ToolBarArea.RightToolBarArea,
    Side.TOP: Qt.ToolBarArea.TopToolBarArea,
    Side.BOTTOM: Qt.ToolBarArea.BottomToolBarArea,
}
# the events of a dock after which its button may have to move to another rail or another place
_PLACEMENT_EVENTS = {QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide}


def describe_dock(dock: QDockWidget, icon: Optional[str] = None, side: Optional[Side] = None, button: bool = True):
    """
    How a dock shows on the rails. A dock that isn't described gets a button with a generic icon.

    :param icon: the mdi6 icon of its button
    :param side: the side of its button while the dock wasn't seen yet (it starts hidden); else that of its dock area, or
                 the bottom for a dock in the area of the preview
    :param button: False for a dock without a button
    """
    if icon is not None:
        dock.setProperty(ICON_PROPERTY, icon)
    if side is not None:
        dock.setProperty(SIDE_PROPERTY, side.value)
    dock.setProperty(BUTTON_PROPERTY, button)


def is_raised(dock: QDockWidget) -> bool:
    """The dock can be seen: it is open and not behind another dock of its tab group (Qt moves those out of the window)."""
    return dock.isVisible() and not dock.visibleRegion().isEmpty()


class RailButton(QAbstractButton):
    """The button of a dock: its icon and title, turned along the rail like in IntelliJ (bottom to top on the left)."""

    ICON_SIZE = 16
    PADDING_ALONG = UiDimensions.one
    PADDING_ACROSS = UiDimensions.half // 2 + 1
    GAP = UiDimensions.half

    def __init__(self, dock: QDockWidget, side: Side, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.dock = dock
        self.side = side
        self.setCheckable(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setText(dock.windowTitle())
        ThemedIcons.apply(self, dock.property(ICON_PROPERTY) or DEFAULT_ICON)
        action = dock.toggleViewAction()
        self.setChecked(action.isChecked())
        action.toggled.connect(self.setChecked)
        # raised or behind another dock of its tab group
        dock.visibilityChanged.connect(self._on_visibility_changed)
        self.clicked.connect(self._on_clicked)

    def _on_visibility_changed(self, _visible: bool):
        self.update()

    def nextCheckState(self):
        # a click doesn't check the button: the dock does, when it is shown or hidden
        pass

    def setText(self, text: str):
        super().setText(text)
        self.setToolTip(text)
        self.updateGeometry()

    def set_side(self, side: Side):
        if side != self.side:
            self.side = side
            self.updateGeometry()
            self.update()

    def _on_clicked(self):
        action = click_action(self.dock.toggleViewAction().isChecked(), is_raised(self.dock))
        if action is RailClick.HIDE:
            self.dock.hide()
        else:
            self.dock.show()
            self.dock.raise_()

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

        alpha = 0
        if self.isChecked():
            alpha = 70 if is_raised(self.dock) else 24
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


class ToolWindowRails(QObject):
    """The rails of a main window, with a button for each of its docks (see the module)."""

    def __init__(self, window: QMainWindow, center: QDockWidget):
        """
        :param center: the dock the others are placed around: the side of a dock is the side of it the dock is on
        """
        super().__init__(window)
        self._window = window
        # the minimum size of the window without the rails
        self._base_minimum = window.minimumSize()
        self._center = center
        self._buttons: Dict[QDockWidget, RailButton] = {}
        # where the button of each dock was put last, by the dock's object name: a hidden dock keeps its place
        self._placements: Dict[str, Placement] = self._load_placements()
        self._order: Dict[Side, List[RailButton]] = {side: [] for side in Side}
        # the tab bars of the tab groups of docks, which QMainWindow creates
        self._tab_bars: Set[QTabBar] = set()

        self.action_show_rails = QAction("Tool window bars", self)
        self.action_show_rails.setCheckable(True)
        self.action_show_rails.setToolTip("Show a button for each panel at the edges of the window")
        self.action_show_rails.setChecked(QSettings().value(SHOW_RAILS_KEY, True, type=bool))
        self.action_show_rails.toggled.connect(self._on_show_rails_toggled)

        # everything that can move a button runs one update, once the layout of the window has settled
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(0)
        self._update_timer.timeout.connect(self.update)

        self._rails: Dict[Side, QToolBar] = {}
        self._layouts: Dict[Side, QBoxLayout] = {}
        for side in Side:
            self._create_rail(side)

        window.installEventFilter(self)
        self.update()

    def _create_rail(self, side: Side):
        rail = QToolBar(f"{side.value.capitalize()} tool window bar", self._window)
        rail.setObjectName(f"rail_{side.value}")
        rail.setProperty("role", "rail")
        rail.setMovable(False)
        rail.setFloatable(False)
        rail.setAllowedAreas(_TOOLBAR_AREAS[side])
        # shown and hidden with the View menu action, not one of its own
        rail.toggleViewAction().setVisible(False)
        container = QWidget()
        direction = QBoxLayout.Direction.TopToBottom if side.vertical else QBoxLayout.Direction.LeftToRight
        layout = QBoxLayout(direction, container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(UiDimensions.half // 2)
        rail.addWidget(container)
        self._window.addToolBar(_TOOLBAR_AREAS[side], rail)
        rail.installEventFilter(self)
        rail.hide()
        self._rails[side] = rail
        self._layouts[side] = layout

    # --- queries ---

    def button(self, dock: QDockWidget) -> Optional[RailButton]:
        return self._buttons.get(dock)

    def rail(self, side: Side) -> QToolBar:
        return self._rails[side]

    def buttons(self, side: Side) -> List[RailButton]:
        """The buttons of a rail, in their order."""
        return list(self._order[side])

    def side_of(self, dock: QDockWidget) -> Optional[Side]:
        """The rail of the button of a dock, None without one."""
        button = self._buttons.get(dock)
        return None if button is None else button.side

    # --- updates ---

    def schedule_update(self, *_args):
        self._update_timer.start()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if watched is self._window:
            # a dock may have been added or removed, or the window shown
            if kind in (QEvent.Type.ChildAdded, QEvent.Type.ChildRemoved, QEvent.Type.Show):
                self.schedule_update()
        elif isinstance(watched, QDockWidget):
            if kind in _PLACEMENT_EVENTS:
                self.schedule_update()
            elif kind == QEvent.Type.WindowTitleChange and watched in self._buttons:
                self._buttons[watched].setText(watched.windowTitle())
        elif kind in (QEvent.Type.Show, QEvent.Type.Hide):
            # a tab bar, or a rail (e.g. by restoring the window state): whether it is shown is decided here
            self.schedule_update()
        return False

    def update(self):
        """Give each dock of the window a button, on the rail where the dock is."""
        self._find_docks()
        tabs = self._tab_indices()
        placements = []
        for dock in self._buttons:
            placement = self._placement(dock, tabs)
            self._placements[dock.objectName()] = placement
            placements.append((dock, placement))
        for side, docks in arrange(placements).items():
            buttons = [self._buttons[dock] for dock in docks]
            if buttons != self._order[side]:
                layout = self._layouts[side]
                for button in buttons:
                    layout.removeWidget(button)
                for index, button in enumerate(buttons):
                    button.set_side(side)
                    layout.insertWidget(index, button)
                self._order[side] = buttons
                layout.parentWidget().adjustSize()
            rail = self._rails[side]
            visible = bool(buttons) and self.action_show_rails.isChecked()
            if rail.isHidden() == visible:
                rail.setVisible(visible)
        self._update_minimum_size()

    def _update_minimum_size(self):
        """The minimum size of the window is that of its docks: the rails need room of their own."""
        width = sum(
            self._rails[side].sizeHint().width() for side in (Side.LEFT, Side.RIGHT) if not self._rails[side].isHidden()
        )
        height = sum(
            self._rails[side].sizeHint().height() for side in (Side.TOP, Side.BOTTOM) if not self._rails[side].isHidden()
        )
        self._window.setMinimumSize(self._base_minimum.width() + width, self._base_minimum.height() + height)

    def _find_docks(self):
        for dock in list(self._buttons):
            if sip.isdeleted(dock) or dock.parent() is not self._window:
                self._remove(dock)
        for dock in self._window.findChildren(QDockWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if dock not in self._buttons and self._has_button(dock):
                self._add(dock)

    @staticmethod
    def _has_button(dock: QDockWidget) -> bool:
        if dock.property(BUTTON_PROPERTY) is False:
            return False
        # a dock that can't be closed is always there: it needs no button
        return bool(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetClosable)

    def _add(self, dock: QDockWidget):
        button = RailButton(dock, Side.LEFT)
        self._buttons[dock] = button
        dock.installEventFilter(self)
        dock.dockLocationChanged.connect(self.schedule_update)
        dock.topLevelChanged.connect(self.schedule_update)
        dock.destroyed.connect(self.schedule_update)

    def _remove(self, dock: QDockWidget):
        button = self._buttons.pop(dock)
        for side in Side:
            if button in self._order[side]:
                self._order[side].remove(button)
        if not sip.isdeleted(button):
            button.setParent(None)
            button.deleteLater()

    def _tab_indices(self) -> Dict[int, int]:
        """:return: the index of each dock of a tab group in its group, by the address of the dock"""
        indices = {}
        self._tab_bars = {bar for bar in self._tab_bars if not sip.isdeleted(bar)}
        for bar in self._window.findChildren(QTabBar, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if bar not in self._tab_bars:
                # the order of the buttons follows the tabs (shown, moved by the user)
                self._tab_bars.add(bar)
                bar.installEventFilter(self)
                bar.tabMoved.connect(self.schedule_update)
            # Qt keeps the tab bars of tab groups that are gone, hidden
            if bar.isVisible():
                for index in range(bar.count()):
                    indices[bar.tabData(index)] = index
        return indices

    def _placement(self, dock: QDockWidget, tabs: Dict[int, int]) -> Placement:
        """Where the button of a dock goes: next to where the dock is, else where it was last."""
        rect = self._shown_rect(dock)
        center = self._shown_rect(self._center)
        if rect is not None and center is not None:
            # QMainWindow gives each tab the address of its dock as data
            return place(rect, center, tabs.get(int(sip.unwrapinstance(dock)), 0))
        known = self._placements.get(dock.objectName())
        if known is not None:
            return known
        side = dock.property(SIDE_PROPERTY)
        if side is None:
            area = self._window.dockWidgetArea(dock)
            # nested in the area of the preview, the area says nothing: below it, like most docks of the window
            side = Side.BOTTOM if area == self._window.dockWidgetArea(self._center) else _AREA_SIDES.get(area, Side.LEFT)
        # after the docks that were seen
        return Placement(Side(side), 1 << 30)

    def _shown_rect(self, dock: QDockWidget) -> Optional[Rect]:
        """Where a dock is in the window, also behind another dock of its tab group; None while it is hidden or floating."""
        if not self._window.isVisible() or dock.isHidden() or dock.isFloating():
            return None
        for member in [dock] + self._window.tabifiedDockWidgets(dock):
            if not member.isFloating() and is_raised(member):
                geometry = member.geometry()
                return Rect(geometry.x(), geometry.y(), geometry.width(), geometry.height())
        return None

    # --- settings ---

    def _on_show_rails_toggled(self, shown: bool):
        QSettings().setValue(SHOW_RAILS_KEY, shown)
        self.update()

    @staticmethod
    def _load_placements() -> Dict[str, Placement]:
        try:
            values = json.loads(QSettings().value(PLACEMENTS_KEY, "{}"))
        except (TypeError, ValueError):
            LOGGER.warning("Ignoring the remembered places of the tool window buttons: they can't be read")
            return {}
        placements = {name: Placement.from_json(value) for name, value in values.items()} if isinstance(values, dict) else {}
        return {name: placement for name, placement in placements.items() if placement is not None}

    def save(self):
        """Remember where the buttons are, for the docks that are hidden at the next start."""
        values = {name: placement.to_json() for name, placement in self._placements.items()}
        QSettings().setValue(PLACEMENTS_KEY, json.dumps(values))
