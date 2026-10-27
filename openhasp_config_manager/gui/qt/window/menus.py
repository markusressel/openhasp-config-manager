from PyQt6.QtGui import QActionGroup, QKeySequence

from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.theme import ThemeMode, current_mode


def create_menus(window):
    """Creates the actions and the menu bar of a `MainWindow`: the actions are attributes of it (`action_save`, ...)."""
    editor = window.page_layout_editor_widget
    create = UiComponents.create_action

    window.action_save = create(
        window,
        "Save",
        "content-save",
        window.draft_actions.save,
        shortcut=QKeySequence.StandardKey.Save,
        tooltip="Write the changes of the draft into the .jsonl files",
    )
    window.action_revert = create(
        window,
        "Revert",
        "restore",
        window.draft_actions.revert,
        tooltip="Discard the changes of the draft and load the files again",
    )
    window.action_deploy = create(
        window,
        "Deploy",
        "upload",
        window.draft_actions.deploy,
        tooltip="Upload the saved files to the plate, like the deploy command of the CLI. "
        "The plate rebuilds its pages, or restarts if its settings or fonts changed.\nUnsaved changes of the draft are not deployed.",
    )
    # next to the files they act on
    window.file_tree_widget.set_actions(
        [(window.action_save, "content-save"), (window.action_revert, "restore"), (window.action_deploy, "upload")]
    )

    file_menu = window.menuBar().addMenu("&File")
    file_menu.addAction(window.action_save)
    file_menu.addAction(window.action_revert)
    file_menu.addSeparator()
    file_menu.addAction(create(window, "Reload devices", "refresh", window.load_plates, shortcut="Ctrl+R"))
    file_menu.addSeparator()
    file_menu.addAction(create(window, "Quit", "exit-to-app", window.close, shortcut=QKeySequence.StandardKey.Quit))

    edit_menu = window.menuBar().addMenu("&Edit")
    for action in [
        editor.action_undo,
        editor.action_redo,
        None,
        editor.action_edit_mode,
        editor.action_snap,
        None,
        editor.action_copy,
        editor.action_paste,
        editor.action_duplicate,
        editor.action_delete,
    ]:
        if action is None:
            edit_menu.addSeparator()
        else:
            edit_menu.addAction(action)

    page_menu = window.menuBar().addMenu("&Page")
    for action in [
        editor.action_previous_page,
        editor.action_next_page,
        None,
        editor.plate.action_clear,
    ]:
        if action is None:
            page_menu.addSeparator()
        else:
            page_menu.addAction(action)

    plate_menu = window.menuBar().addMenu("P&late")
    for action in [editor.plate.action_live_preview, editor.plate.action_restore_plate, None, window.action_deploy]:
        if action is None:
            plate_menu.addSeparator()
        else:
            plate_menu.addAction(action)

    view_menu = window.menuBar().addMenu("&View")
    for action in [editor.action_zoom_in, editor.action_zoom_out, editor.action_zoom_fit]:
        view_menu.addAction(action)
    view_menu.addSeparator()
    for dock in [window.devices_dock, window.properties_dock, window.jsonl_dock, window.page_jsonl_dock, window.logs_dock]:
        view_menu.addAction(dock.toggleViewAction())
    view_menu.addSeparator()
    view_menu.addAction(
        create(
            window,
            "Restore default layout",
            "view-dashboard-outline",
            window.restore_default_layout,
            tooltip="Show all panels again and put them back where they were at the first start",
        )
    )
    view_menu.addSeparator()

    theme_menu = view_menu.addMenu("Theme")
    theme_group = QActionGroup(window)
    for mode, title, icon in [(ThemeMode.DARK, "Dark", "weather-night"), (ThemeMode.LIGHT, "Light", "weather-sunny")]:
        action = create(window, title, icon, lambda mode=mode: window.set_theme(mode), checkable=True)
        action.setChecked(current_mode() == mode)
        theme_group.addAction(action)
        theme_menu.addAction(action)
