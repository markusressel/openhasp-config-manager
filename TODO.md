# TODO

Findings from a review of `openhasp_config_manager/gui` (PyQt6 page layout editor and plate controls).

## 1. Structure and cleanup

- [ ] Move `gui/util.py` (console helpers `error`, `warn`, `info`, `success`, `echo`, `print_diff_to_console`) out of the `gui` package. It is
  CLI code, and all of `cli/*.py` imports it from `gui`.
- [ ] Delete `gui/qt/file_browser.py`: nothing imports it, `clear_entries` calls `clear_layout(self.layout)` on a `QTreeWidget` (broken), and it
  loads icons from the relative path `assets/*.ico`.
- [ ] Split `gui/qt/util.py` (icon parsing, `clear_layout`, global asyncio loop, `ThreadBridge`, `qBridge`, `run_async`) into focused modules and
  move the mid-file imports to the top.
- [ ] Replace the `print()` calls (`page_layout_editor.py`, `property editor`, ...) with a logger.
- [ ] Stop shadowing `QWidget.layout()` with `self.layout = ...` in widgets.
- [x] `run_async`: run `on_done` even if `on_success` raises (a failed callback leaves the deploy button disabled).
- [ ] Remove the commented-out code in `MainWindow.select_device`.

## 2. Session and editing bugs

- [ ] `PlateSession.is_dirty`, `commit_to_snapshot()` and `reset_to_disk()` are never used: edits cannot be saved. Add "Save" (write the draft
  back to the `.jsonl` files of its components), "Revert" and a dirty indicator.
- [ ] `MainWindow.load_plates()` runs `analyze()` on every device click and builds new `Device` objects, while `sessions` is keyed by `Device`.
  Key the sessions by `device.name` (check `Device.__eq__`/`__hash__`), so a draft survives re-selecting a device.
- [ ] `PageLayoutEditorWidget.set_data` loads from disk only when `working_objects` is empty: selecting another cmd component reuses the stale
  draft. Keep one draft per (device, cmd component), or reload on change.
- [x] Removing an object only searches `jsonl_components[0]`. Search all components of the draft.
- [ ] `get_page_objects` drops objects with `hidden: true`, so they cannot be selected or edited. Show them dimmed instead.
- [x] Deploy sends one object every 100 ms with no progress and no error feedback. Report progress and failures in the UI.
- [ ] Tests for the Qt-free parts: `PlateSession`, `get_page_objects`, page index navigation (extract them from the widget into a plain class).

## 3. Live editing on the real device, built on the composition system

Goal: what the user does in the editor shows up on the real plate in near real time, and the "Sync with Real Device" switch becomes the
switch for exactly that.

Today "sync" only mirrors the page number (`OpenHaspClient.set_page`), and "Deploy" clears the page and re-sends every object. The code-defined
layouts (`haad/layout`, `haad/page`, `haad/plate`) already have most of the machinery for incremental updates:

- `Page.relayout()` re-runs the layout and sends only the changed `x`/`y`/`w`/`h`, updating `obj.jsonl` in place.
- `Repeat` adds an object with a single JSONL message (`client.jsonl`) and removes one with `delete_object_id`, keeping `page.objects` and
  `plate.rendered` current.
- Objects have stable ids (`pXbY`), so a change can address one object.
- `dump.py` and `render.py` turn a layout into JSONL objects.

Plan:

- [ ] **One edit model.** Make the editor emit small edit operations (`add(obj)`, `remove(id)`, `set(id, property, value)`, `move/resize(id, rect)`)
  on the `PlateSession` draft instead of mutating dicts in the widget. The preview, the JSONL view, the dirty state and the live sync all
  subscribe to the same operations.
- [ ] **Diff, don't redeploy.** A live-sync service turns each operation into the minimal openHASP command: a property change is
  `p1b5.text="..."`, a move is `x`/`y`/`w`/`h`, a remove is `p1b5.delete`, an add is a single JSONL line. "Deploy" stays as the full resync (also
  to recover from drift), and runs automatically when live sync is switched on.
- [ ] **Coalesce.** Debounce rapid changes (dragging, typing): keep only the last value per `(object, property)` and send it every ~50–100 ms.
  Never queue one message per mouse move.
- [ ] **Ordering and ids.** Check how the editor assigns object ids and whether they are stable when objects are added or removed. Z-order follows
  creation order on the plate, so reordering needs a delete and re-add of the objects above.
- [x] **Failure handling.** Show connection state in the controls (connected, sending, out of sync, failed). If a message fails, mark the plate
  "out of sync" and offer a resync, don't retry silently. (Done for Deploy and Clear; the live sync operations must report to it too.)
- [ ] **Edit the code-defined pages, not only JSONL.** Render a `Page` of the composition system into the preview with `render.py`/`dump.py`, so
  the editor can show pages like the alerts page. Unlike JSONL pages these have no file to write back to, so the editor shows them read-only
  at first, and the live connection shows the real runtime values.
- [ ] **Layout-aware editing of composed pages.** For `Column`/`Row`/`Panel` trees, an edit of a property such as `gap`, `padding` or `size` runs
  `relayout()` and sends the diff. This is the same path haad uses at runtime for collapsed or repeated items.
- [ ] **Preview from the real plate (optional).** Subscribe to the plate's state topics so the preview shows touch events and values coming from
  the device, and clicking in the preview can trigger the same action as touching the plate.
- [ ] Verify on a real plate what is still unverified from the runtime work: `delete` cascading to children, a single JSONL add onto a shown
  page, and `x`/`y`/`w`/`h` commands.

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
- [ ] Confirm dialogs for Revert and "unsaved changes" on device switch and close: need Save/Revert (section 2) first.
- [x] Keyboard shortcuts: delete (Del), duplicate (Ctrl+D), arrow keys to nudge (Shift: 10 px), page left/right (Alt+Left/Right, PgUp/PgDn),
  edit mode (Ctrl+E), snap (Ctrl+G), zoom (Ctrl++/-/0), reload (Ctrl+R). Undo/redo is the item below.
- [ ] Undo/redo, which comes with the edit model of section 3.
- [x] Snap to grid and alignment guides when dragging in the preview.
- [x] Widget property editor: group properties (position, size, style, behaviour), proper editors for colors and icons, and validation with
  inline errors.
- [x] Widget picker: icons and a short description per widget.
- [x] A scroll wrapper and sensible minimum sizes, so a small window does not clip the controls.
