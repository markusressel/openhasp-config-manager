# TODO

Findings from a review of `openhasp_config_manager/gui` (PyQt6 page layout editor and plate controls).

## 1. Structure and cleanup

- [x] Move `gui/util.py` (console helpers `error`, `warn`, `info`, `success`, `echo`, `print_diff_to_console`) out of the `gui` package. It is
  CLI code, and all of `cli/*.py` imports it from `gui`. (Now `openhasp_config_manager/console.py`: the manager, uploader, template rendering
  and `OpenHaspClient` use it too.)
- [x] Delete `gui/qt/file_browser.py`: nothing imports it, `clear_entries` calls `clear_layout(self.layout)` on a `QTreeWidget` (broken), and it
  loads icons from the relative path `assets/*.ico`.
- [x] Split `gui/qt/util.py` (icon parsing, `clear_layout`, global asyncio loop, `ThreadBridge`, `qBridge`, `run_async`) into focused modules and
  move the mid-file imports to the top. (`gui/qt/icons.py`, `gui/qt/layouts.py`, `gui/qt/async_bridge.py`)
- [x] Replace the `print()` calls (`page_layout_editor.py`, `property editor`, ...) with a logger.
- [x] Stop shadowing `QWidget.layout()` with `self.layout = ...` in widgets.
- [x] `run_async`: run `on_done` even if `on_success` raises (a failed callback leaves the deploy button disabled).
- [x] Remove the commented-out code in `MainWindow.select_device`.

## 2. Session and editing bugs

- [x] `PlateSession.is_dirty`, `commit_to_snapshot()` and `reset_to_disk()` are never used: edits cannot be saved. Add "Save" (write the draft
  back to the `.jsonl` files of its components), "Revert" and a dirty indicator. (The draft keeps each object's source with its templates;
  Save patches only the changed properties into the files, see `processing/jsonl/source_editor.py`, and asks before changing `common/` files.)
- [x] Templates in the editor: every property can be switched to a Jinja template, with the variables of a deployment as suggestions
  (`DeviceProcessor.jsonl_template_variables`) and the rendered value shown below it.
- [ ] Insert template variables inside longer texts (the suggestions replace the whole value today).
- [x] Choose the file new objects go into: the Files tree in the sidebar shows `common/` and the device folder with their subfolders,
  the pages of each loaded .jsonl file, highlights a file's objects, and double-click makes a file the target. Without a choice, new
  objects go into the device's own file with the most objects on the page, never into a shared one unless the device has none.
- [ ] Files tree, next steps: "New .jsonl file here" on a folder (adds the `run L:/<flattened name>` line to the right .cmd and checks
  the 30 character limit), and "Move to file" for an object.
- [x] Remember the editor session across restarts, per config directory: the selected device and the chosen target file per device
  (`gui/domain/ui_session.py`, stored by `gui/qt/ui_session_store.py`; new state is a dataclass field with a default).
- [ ] Templates that refer to other objects (`{{ p1b5.x }}`) are rendered with the objects as they are on disk, not with the draft.
- [ ] A template that is not valid yet is lost when the property panel is rebuilt (e.g. after moving the object).
- [ ] Checking a template for a numeric property that renders to text logs a traceback from `ObjectDimensionsProcessor` (it logs
  failed conversions with `LOGGER.exception` and `print`); log one line instead.
- [x] The brightness slider of the device controls sends a command for every value while dragging; throttle it (50 ms, the last value is always sent).
- [x] `MainWindow.load_plates()` runs `analyze()` on every device click and builds new `Device` objects, while `sessions` is keyed by `Device`.
  Key the sessions by `device.name` (check `Device.__eq__`/`__hash__`), so a draft survives re-selecting a device.
- [x] `PageLayoutEditorWidget.set_data` loads from disk only when `working_objects` is empty: selecting another cmd component reuses the stale
  draft. Keep one draft per (device, cmd component), or reload on change.
- [x] Removing an object only searches `jsonl_components[0]`. Search all components of the draft.
- [x] `get_page_objects` drops objects with `hidden: true`, so they cannot be selected or edited. Show them dimmed instead.
- [x] Deploy sends one object every 100 ms with no progress and no error feedback. Report progress and failures in the UI.
- [x] Tests for the Qt-free parts: `PlateSession`, `get_page_objects`, page index navigation (extract them from the widget into a plain class).

## 3. Live editing on the real device, built on the composition system

Goal: what the user does in the editor shows up on the real plate in near real time.

The editor has three plate actions with tooltips: **Live preview** (the draft on the plate while editing, nothing stored), **Restore plate**
(rebuild all pages from the files on the plate, like a restart: `OpenHaspClient.restore_from_files`) and **Deploy** (upload the saved files
like the CLI, restart if anything changed: `deployment.deploy_device`). "Revert" stays the name for discarding the draft, "Undo" is left
for undo/redo. The code-defined layouts (`haad/layout`, `haad/page`, `haad/plate`) already have most of the machinery for incremental updates:

- `Page.relayout()` re-runs the layout and sends only the changed `x`/`y`/`w`/`h`, updating `obj.jsonl` in place.
- `Repeat` adds an object with a single JSONL message (`client.jsonl`) and removes one with `delete_object_id`, keeping `page.objects` and
  `plate.rendered` current.
- Objects have stable ids (`pXbY`), so a change can address one object.
- `dump.py` and `render.py` turn a layout into JSONL objects.

Plan:

- [ ] **One edit model.** Make the editor emit small edit operations (`add(obj)`, `remove(id)`, `set(id, property, value)`, `move/resize(id, rect)`)
  on the `PlateSession` draft instead of mutating dicts in the widget. The preview, the JSONL view, the dirty state and the live sync all
  subscribe to the same operations.
- [x] **Diff, don't redeploy.** Live preview compares the page with what it last sent (`gui/domain/live_preview.py`): a changed object
  is one JSONL message with only the changed properties, a removed one `p1b5.delete`, a new one a single JSONL line. Turning it on or
  switching the page clears the page and sends it in full; so does a removed property or a changed `obj`, which no command can undo.
  Open: an object whose id changed is deleted and added again, so it ends up on top of the others on the plate.
- [x] **Coalesce.** Live preview sends at most every 50 ms while dragging or typing, and always the last state.
- [ ] **Ordering and ids.** Check how the editor assigns object ids and whether they are stable when objects are added or removed. Z-order follows
  creation order on the plate, so reordering needs a delete and re-add of the objects above.
- [x] **Failure handling.** Show connection state in the controls (connected, sending, out of sync, failed). If a message fails, mark the plate
  "out of sync" and offer a resync, don't retry silently. (Live preview, Clear page and Restore plate report to it. The resync sends the
  page again with Live preview on, and restores the plate without.)
- [ ] **Edit the code-defined pages, not only JSONL.** Render a `Page` of the composition system into the preview with `render.py`/`dump.py`, so
  the editor can show pages like the alerts page. Unlike JSONL pages these have no file to write back to, so the editor shows them read-only
  at first, and the live connection shows the real runtime values.
- [ ] **Layout-aware editing of composed pages.** For `Column`/`Row`/`Panel` trees, an edit of a property such as `gap`, `padding` or `size` runs
  `relayout()` and sends the diff. This is the same path haad uses at runtime for collapsed or repeated items.
- [ ] **Preview from the real plate (optional).** Subscribe to the plate's state topics so the preview shows touch events and values coming from
  the device, and clicking in the preview can trigger the same action as touching the plate.
- [ ] **Compare the draft with the plate (postponed).** Show which objects of the editor differ from what the plate has in memory right now.
  openHASP 0.7.0 has no command to list objects, dump a page or read a whole object back: only single property getters
  (`command/p1b2.text` with an empty payload answers on `state/p1b2`, see `OpenHaspClient.get_object_property`). So only the objects the
  draft knows can be compared, one round trip per property (e.g. `x`, `y`, `w`, `h`, `text`, `val`, `hidden`). Objects that exist only on the
  plate stay invisible; probing every id was rejected. Screenshots (`take_screenshot`) were rejected as well.
- [ ] Verify on a real plate what is still unverified from the runtime work: `delete` cascading to children, a single JSONL add onto a shown
  page, and `x`/`y`/`w`/`h` commands.
- [ ] Verify Restore plate on a real plate: whether `clearpage all` also clears page 0, and whether `run /pages.jsonl`, `page`,
  `run /boot.cmd`, `run /online.cmd` rebuild it like a restart (the docs don't give the startup order).

## 4. UI polish

### Loading states
- [x] Show a loading state while `analyze()` runs (device list), while a cmd component loads, and while the processor normalizes the JSONL.
  Run them through `run_async` so the window stays responsive.
- [x] Disable the buttons and show a spinner or progress bar for Deploy, Clear Page and the live sync, until the operation finished.
- [x] Replace `setEnabled(False)` / `setEnabled(True)` pairs by one busy helper that also restores on error.

### Empty states
- [x] No devices found: explain where the config directory is and how to add a device.
- [x] No device selected: today the controls and editor are simply hidden. Show a placeholder with a hint instead.
- [x] Device without pages or objects: placeholder with an "Add object" action.
- [x] Empty page: show the empty plate with a hint instead of a blank canvas.
- [x] No object selected: the property editor shows a short hint.
- [x] Error states: device unreachable, config failed to load or validate, with the error text and a retry button.
  (Validation does not run in the GUI yet, so there is no state for validation errors.)

### General cleanup
- [x] One layout: a left sidebar with the device list, a central canvas (the plate preview with the exact plate aspect ratio and zoom), a right
  inspector (properties), and the JSONL view as a collapsible bottom panel. Today everything is stacked in one column.
- [x] A toolbar for the editor controls (previous/next page, page selector, sync, deploy, clear) with icons and tooltips, and a status bar for
  dirty state and the last operation.
- [x] Connection state in the status bar: MQTT broker reachable, the plate's LWT (online/offline), sending, and pages out of sync
  after a failed deploy or a clear (click to deploy again).
- [x] A consistent theme: replace the per-widget `setStyleSheet` padding strings with one application stylesheet and the `UiDimensions` scale.
  Support a dark theme.
- [x] Confirm dialogs for Clear Page, removing objects and rebooting the device.
- [x] Confirm dialogs for Revert and "unsaved changes" on close. (Drafts survive a device switch, so it doesn't ask there.)
- [x] Keyboard shortcuts: delete (Del), duplicate (Ctrl+D), arrow keys to nudge (Shift: 10 px), page left/right (Alt+Left/Right, PgUp/PgDn),
  edit mode (Ctrl+E), snap (Ctrl+G), zoom (Ctrl++/-/0), reload (Ctrl+R). Undo/redo is the item below.
- [ ] Undo/redo, which comes with the edit model of section 3.
- [x] Snap to grid and alignment guides when dragging in the preview.
- [x] Widget property editor: group properties (position, size, style, behaviour), proper editors for colors and icons, and validation with
  inline errors.
- [x] Widget picker: icons and a short description per widget.
- [x] A scroll wrapper and sensible minimum sizes, so a small window does not clip the controls.

## 5. Packaging and installation

The GUI dependencies (PyQt6, QtAwesome, qt-themes, pfzy) are in the optional Poetry group `ui` because the GUI is still a work in
progress. They should stay optional, but a Poetry group only exists in the development checkout: `pip install openhasp-config-manager`
never installs it, so the published package can't run `openhasp-config-manager gui` today.

- [ ] Decide how users choose what to install, e.g.:
  - extras of one package: `openhasp-config-manager` (CLI and API client), `openhasp-config-manager[gui]`, `openhasp-config-manager[tui]`;
  - or separate packages: a small API client (`openhasp_client`, used by haad and AppDaemon), the CLI, and the GUI on top of it.
- [ ] Keep the API client free of CLI and GUI dependencies (click, PyQt6, …), so haad and AppDaemon projects only pull what they use.
  (`OpenHaspClient` still imports the console helpers from `openhasp_config_manager.console`.)
- [ ] The `gui` command (and a future TUI) explains which extra to install when its dependencies are missing, instead of an ImportError.
- [ ] Move the dependencies to `[project.optional-dependencies]` (or Poetry extras) accordingly, and clean up the `[project]` table of
  `pyproject.toml`, which only has a name and a version next to the Poetry configuration.
- [ ] Update the Dockerfile, the README installation instructions, `venv-install` in the Makefile and the CI (which installs without `ui`,
  so the GUI tests are skipped there).
