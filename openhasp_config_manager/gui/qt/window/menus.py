from PyQt6.QtGui import QActionGroup, QKeySequence

from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.theme import ThemeMode, current_mode


def create_menus(window):
    """Creates the actions and the menu bar of a `MainWindow`: the actions are attributes of it (`action_save`, ...)."""
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
    window.action_deploy_purge = create(
        window,
        "Deploy and remove other files…",
        "delete-sweep",
        lambda: window.draft_actions.deploy(purge=True),
        tooltip="Deploy, and delete the files on the plate that the deploy doesn't upload, like the deploy command of the "
        "CLI with --purge.\nThey are listed before anything is deleted.",
    )
    # next to the files they act on
    window.file_tree_widget.set_actions(
        [(window.action_save, "content-save"), (window.action_revert, "restore"), (window.action_deploy, "upload")]
    )

    file_menu = window.menuBar().addMenu("&File")
    file_menu.addAction(window.action_save)
    file_menu.addAction(window.action_revert)
    file_menu.addSeparator()
    file_menu.addAction(window.action_deploy)
    file_menu.addAction(window.action_deploy_purge)
    file_menu.addSeparator()
    file_menu.addAction(create(window, "Reload devices", "refresh", window.load_plates, shortcut="Ctrl+R"))
    file_menu.addSeparator()
    file_menu.addAction(create(window, "Quit", "exit-to-app", window.close, shortcut=QKeySequence.StandardKey.Quit))

    # the actions of the editor of the active tab (see `show_editor_actions`)
    window.edit_menu = window.menuBar().addMenu("&Edit")
    window.page_menu = window.menuBar().addMenu("&Page")
    window.plate_menu = window.menuBar().addMenu("P&late")

    view_menu = window.menuBar().addMenu("&View")
    # the zoom actions of the editor go before it
    window.view_menu = view_menu
    window.zoom_actions_end = view_menu.addSeparator()
    window.zoom_actions = []
    for dock in [
        window.devices_dock,
        window.properties_dock,
        window.jsonl_dock,
        window.page_jsonl_dock,
        window.logs_dock,
        window.plates_dock,
    ]:
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
    show_editor_actions(window, window.page_layout_editor_widget)


def show_editor_actions(window, editor):
    """Fill the menus of the editor actions with those of an editor: each tab has its own."""
    for menu, actions in [
        (
            window.edit_menu,
            [
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
            ],
        ),
        (window.page_menu, [editor.action_previous_page, editor.action_next_page, None, editor.plate.action_clear]),
        (
            window.plate_menu,
            [editor.plate.action_live_preview, editor.plate.action_restore_plate, None, window.action_deploy],
        ),
    ]:
        menu.clear()
        for action in actions:
            if action is None:
                menu.addSeparator()
            else:
                menu.addAction(action)
    for action in window.zoom_actions:
        window.view_menu.removeAction(action)
    window.zoom_actions = [editor.action_zoom_in, editor.action_zoom_out, editor.action_zoom_fit]
    window.view_menu.insertActions(window.zoom_actions_end, window.zoom_actions)
