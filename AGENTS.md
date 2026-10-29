# openhasp-config-manager: Guide for AI Agents

openhasp-config-manager manages the configuration of [openHASP](https://www.openhasp.com) touch panels ("plates") from one config
directory: it preprocesses `*.jsonl`/`*.cmd` files (Jinja2 templates, variables), validates them and deploys them over MQTT/HTTP.
It also contains an async client for plates, a PyQt6 GUI (page layout editor), and integrations for AppDaemon and haad.

User documentation lives in `README.md`. Known issues and plans live in `TODO.md`.

## Ecosystem

This repository is checked out next to the haad repositories (e.g. under `/home/markus/programming/PycharmProjects/`):

- `../haad`: the home automation framework. It uses this repository as an editable dependency, and its `AGENTS.md` is the source of
  truth for haad's rules.
- `../haad-home`: the house. Uses `openhasp_config_manager.haad` to drive the plates.

Changes to public APIs of `openhasp_config_manager.haad` or `openhasp_config_manager.openhasp_client` can break `haad-home`. Search
`../haad-home` for usages before changing or removing them.

## Setup

- Python: 3.13 for this repository (`.python-version`), `>=3.12,<3.15` supported. The haad integration needs Python 3.14 (see Testing).
- Dependencies: `poetry install --extras gui` (the `gui` extra is optional; AppDaemon and haad are not extras, see Testing). A `.venv` in the repository root is used by the commands below.
- Run the CLI: `.venv/bin/openhasp-config-manager --help`, e.g. `gui -c ./openhasp-configs`.

## Commands

| Task                         | Command                                                     |
|------------------------------|-------------------------------------------------------------|
| Tests                        | `make test` (= `cd tests && poetry run pytest`, 100 % coverage of `processing/template_rendering.py` required) |
| Single test                  | `cd tests && ../.venv/bin/pytest manager_analyze_test.py -k <name>` |
| haad integration tests       | `make test-haad` (runs in `../haad`'s uv environment, 100 % coverage required) |
| Lint (CI runs `ruff check .`) | `make lint`                                                |
| Check a config directory     | `.venv/bin/openhasp-config-manager check -c <dir> [--json]` (`check.py`) |
| Format                       | `make format`                                               |
| Docker image                 | `make docker-latest`                                        |

`codespell` runs in CI; add false positives to `.codespellignore`.

## Repository layout

| Path                                         | Purpose                                                                       |
|----------------------------------------------|-------------------------------------------------------------------------------|
| `openhasp_config_manager/cli/`               | Click commands (`deploy`, `upload`, `generate`, `gui`, `cmd`, `state`, ...).  |
| `openhasp_config_manager/manager.py`         | `ConfigManager`: analyzes the config directory, processes and deploys it.     |
| `openhasp_config_manager/processing/`        | Preprocessing of JSONL/CMD files (templates, variables, normalization).       |
| `openhasp_config_manager/validation/`        | Validators for the processed files.                                           |
| `openhasp_config_manager/openhasp_client/`   | `OpenHaspClient` (MQTT, HTTP, telnet) and the config/device models.           |
| `openhasp_config_manager/gui/`               | PyQt6 GUI. `gui/domain/` holds Qt-free logic, `gui/qt/` the widgets.          |
| `openhasp_config_manager/haad/`              | haad integration: plate controllers, code-defined layouts (`layout/README.md`).|
| `openhasp_config_manager/ad/`                | AppDaemon integration.                                                        |
| `openhasp-configs/`                          | The user's own config directory (gitignored, see Agent guidelines).           |
| `tests/`                                     | pytest tests, `tests/_test_cfg_root` is the config directory used by them.    |

## Code style

- 4-space indent for Python, 2 spaces otherwise (`.editorconfig`). Ruff with line length 127 (`pyproject.toml`).
- Type hints on public functions. Use `logging` (module loggers), not `print()`, except for user-facing CLI output (`console.py`).
- Fail fast: no defensive fallbacks that hide configuration or programming errors.
- GUI: keep logic that does not need Qt in `gui/domain/` so it can be tested without a display. Long-running work (config analysis,
  device communication) runs through `run_async` (`gui/qt/async_bridge.py`) so the window stays responsive; never block the Qt main thread.
- Templates: everything that renders or inspects a Jinja2 template goes through `processing/template_rendering.py` (nested templates,
  unknown variables staying as written, ...). Don't use `jinja2` directly elsewhere; add a test there for every new case (100 % coverage).
- Directives (`!include`, README "Including objects", design in `docs/include-directive.md`): `processing/jsonl/includes.py` expands
  them (`expand_includes`) before the object references are resolved, so the object map of `pXbY` contains the included objects,
  each with the scope of its instance. Every expanded object has an `ObjectOrigin` (part file, line, chain of `IncludeStep`s);
  report problems of included objects at the part with that chain (`check.py`, the GUI). A part only counts through its instances:
  it is uploaded only if a `.cmd` runs it. Code that reads the objects of a file must go through
  `DeviceProcessor.expand_jsonl_objects`, not the raw sources, or it misses included objects and sees directives as objects.
- `OpenHaspClient` is async: every call must be awaited. A missing `await` fails silently (the coroutine never runs), which once broke
  deploy, upload and screenshots.

## GUI editor

- **Draft**: `PlateSession` (`gui/domain/draft/session.py`) keeps every object twice: rendered (shown in the preview) and as written in its
  file, with its templates. Change objects through the session (`set_source_value`, `add_object`, `paste_objects`, ...), never by
  mutating the rendered dicts: Save patches only the changed source properties back into the files. The session reports every
  finished edit, undo and redo to its listeners (`DraftChange`); `PageLayoutEditorWidget._on_draft_changed` updates the preview,
  the JSONL, the properties, the dirty state, the undo actions and Live preview from it. An edit operation only changes the
  session, it doesn't refresh anything itself.
- **Undo/redo**: every change through the session is a step of its undo history (`gui/domain/draft/edit_history.py`, whole states of
  the sources, so undo doesn't depend on how an edit was made). Group the changes of one user action with
  `with session.edit("Move 3 objects"):`, and pass a `merge_key` for actions repeated in a row (typing into a property, nudging). An
  edit operation of the editor needs no undo code of its own, only the grouping. Save doesn't load the draft again: the
  draft takes what it wrote as its files (`mark_saved`), so the history continues. It starts anew when the draft is loaded from
  changed files or reverted.
- **Interact mode** (*Edit* off): touches go through `Indev` (`gui/domain/interaction.py`, a port of the LVGL input device: press lost,
  long press, release) to the items, which are its targets. What a touch changes is `RuntimeState` of the preview, next to the draft and
  never in it: items draw from `EditableWidget.data` (the draft plus these values), and when the draft changes a property that was
  touched, the draft wins. Turning on *Edit* and *Reset* clear it, switching pages keeps it. Behavior ported from the firmware and LVGL
  (which object runs `action`, groups, slider/arc math, dropdown list layout, roller snapping, dragging and throwing, tabview swipes)
  lives in Qt-free `gui/domain/touch_*.py`, `dropdown_list.py`, `roller_scroll.py`, `drag_scroll.py`, `tab_swipe.py`, `bar_values.py` and `lvgl_colors.py`;
  pressed colors can't be measured and are computed there. Port from the sources the plates run (openHASP 0.7.0-rc13, LVGL v7.11),
  not from newer LVGL docs, and say in the docstring which function a port follows. The firmware sets the properties of an object in
  the order of the file, so key order can matter (e.g. a slider `type` after `start_value` resets it). LVGL does this per read of the
  touch (every 20 ms), in whole pixels: the items read the finger with a timer, and tests call the read themselves
  (`ScrollDriver.tick`, `HaspTabviewItem.read_swipe`) and end animations with `finish_animation()` instead of waiting.
  An `action` that sets a property of an object (`p1b2.val=50`, `touch_actions.object_command`) changes it in the preview; every
  other command is only reported (`commandRequested`).
- **Included objects are read-only** in the draft: `PlateSession` keeps a draft copy of the directives of a file and saves its
  plain objects around them. Edit operations check `session.read_only_reason(obj)` (or `_check_editable`, which raises
  `ReadOnlyObjectError`); `origin_of` says where an included object is written. New edit operations must respect this. Only
  the `vars` and `for` of the outermost `!include` change, through `set_directive_value`, which includes the directive again
  (objects of instances that stay keep their rendered dict). In part mode (`enter_part_mode`) the objects of one instance of
  a part can be changed: edits go into the draft copy of the part (`PartDraft`), every instance follows (`_reinclude`), and
  everything else is read-only. `read_only_reason` and `is_selectable` depend on the mode: use them, not `is_included`.
  A part that no page includes is shown on its own (`load_part_alone`, `MainWindow.part_alone`): a draft of one `!include`
  that is in no file (`ComponentSource.is_scratch`, never saved), so `window.session` is then not the draft of the pages.
- **Templates are never replaced implicitly.** Objects whose `x`/`y` is a template or a percentage can't be dragged or nudged; the
  editor explains why, and "Use pixels for x/y" replaces them only when the user asks. Keep this for new edit operations.
- **Files**: new objects go into the target file chosen in the Files tree (`gui/domain/file_tree.py` follows the folder structure of
  `README.md`), by default the device's own file, never a shared `common/` file unless the device has none: saving a shared file changes
  every device that loads it.
- **File operations** of the Files tree (new file/folder, rename, move, delete to the trash): `gui/domain/file_operations.py` makes a
  `FilePlan` (Qt-free), `gui/qt/window/file_actions.py` asks and carries it out. The plate knows a file by its flattened path
  (`common/page/md/content.jsonl` is `L:/common_page_md_content.jsonl`), so a rename or move also changes the `L:/<name>` references of
  the devices that see the file and the `!include` paths. Refused: what the config needs (`common`, `devices`, device folders, their
  `config.json` and startup scripts; `boot.cmd` can't be deleted), anything that leaves a `.cmd` running a missing file (the device
  couldn't be loaded), a name a device already has on the plate, a run file longer than 30 characters, and files with unsaved changes.
- **Changes on disk** (an LLM or editor edits the config directory while the GUI runs): `ConfigWatcher` (`gui/qt/config_watcher.py`,
  watchdog, debounced) reports changed paths to `MainWindow._on_config_changed`. A draft without changes reloads quietly (same page and
  zoom; a failing reload keeps what is shown and reports it in the status bar). A draft with changes is never replaced: a banner offers
  *Reload from disk* or *Keep my changes*. Writes of the app itself (Save) are recognized by content (`OwnWrites`), so they don't count.
- **Text editor** (the *Code* dock: `CodeView` with Source / Split / Rendered): every open file is a `SourceBuffer`
  (`gui/domain/source/buffers.py`, Qt-free) in a tab of `SourceEditorWidget`, independent of the object draft. The syntax (highlighting,
  templates) is `gui/domain/source/syntax.py`, issues while typing `issues.py`, edits `edit.py`, completion
  `completion.py`, objects of a text (folding, the object at the cursor) `objects.py`, `rename.py`,
  `format.py`, hover texts `docs.py`, the placeholders of openHASP (`"text": "%ip%"`) `placeholders.py`, references between files `links.py` (all in `gui/domain/source/`); `CodeEditor`
  (`gui/qt/widgets/code_editor/editor.py`, with the helpers for search, folding, edits, values, completion and hover next to it) only wires them to Qt. Keep that split: logic goes into the
  domain modules with tests, the widget stays thin. Tabs follow disk changes through `MainWindow._on_config_changed`
  (`external_changes`: clean tabs reload, tabs with changes show a banner). Saving a tab goes through `_on_source_saved`, which treats
  it like an external change for the draft (reload, or the *Reload from disk* banner if the draft has changes). `SourceEditorSync`
  (`gui/qt/window/source_sync.py`) connects the editor with the draft: selecting an object shows its line, the cursor selects its object,
  the problems of the page are marked in their files, open tabs are remembered in `UiSession.open_files`. A new editor feature needs a test in `tests/gui/code_editor_test.py` or `source_editor_test.py`.
- **State file**: the GUI writes `<config dir>/.openhasp-config-manager/gui-state.json` for tools that edit the config files next to it
  (what is open, the text editor tabs, selection, draft, problems, load errors, connection). The format is documented in `README` in `gui/domain/gui_state.py`
  (written into that folder). `MainWindow._collect_gui_state` builds it, `GuiStatePublisher` writes it debounced. When you add state
  worth knowing for such tools, add it there, bump `SCHEMA_VERSION` only for breaking changes, and keep that README current. Never put
  credentials or plate configuration in it. Next to it, `GuiStatePublisher` writes `preview.png`, the plate as the preview shows it
  (`render_plate` in `gui/qt/preview_image.py`, which the `preview` command uses too, for pages of the files on disk).
- **Plate actions** (`PlateLink` in `gui/qt/widgets/pagelayout/plate_link.py`, names and tooltips agreed with the user): *Live preview* sends the draft to the plate while editing (nothing is stored
  on it), *Restore plate* rebuilds the pages from the files on the plate like a restart, *Deploy* uploads the saved files. *Revert*
  discards the draft; *Undo*/*Redo* step through the edits of the draft.
- **Remembered state**: what should survive a restart for a config directory or a device goes into `UiSession`/`DeviceSession`
  (`gui/domain/ui_session.py`) as a dataclass field with a default, then `ui_session.save()` (`gui/qt/ui_session_store.py`). App-wide
  preferences (window geometry, theme, view toggles) are plain `QSettings` keys.
- **Preview controls** float inside the preview (`PagePreviewWidget.add_overlay`); `fit_to_view` keeps their rows free, so the plate is
  never covered. Messages about an object go next to it (`show_message`), errors also to the status bar (`OperationStatus.failed`).
- **Logs**: `openhasp_client/logs.py` (Qt-free) parses the telnet output into `LogEntry`s (`segments()` are the parts a CLI or GUI styles)
  and `follow_logs` reconnects with a growing delay; the `logs` command and the Logs dock (`gui/qt/log_stream.py`, `widgets/log_view.py`)
  both use it. The plate only allows one telnet connection, a second one is closed while logging in, so the dock connects only while it
  is visible. The level of a line is the ANSI color the plate sends (`debug.ansi`), otherwise it is guessed from tag and words.

## Testing

- Add or adjust tests with every behavioural change. `pytest-asyncio` runs in auto mode (`tests/pytest.ini`).
- `tests/haad` and `tests/ad` are skipped unless haad or AppDaemon are installed (`tests/conftest.py`), `tests/gui` unless the `gui`
  extra is. CI runs the core, `gui` and `ad` tests as separate jobs (`.github/workflows/pythonpackage.yml`); AppDaemon needs Python <3.14. `tests/haad/README.md`
  explains the haad test setup (golden masters, `FakePlate`).
- The GUI can be checked headless with `QT_QPA_PLATFORM=offscreen` and `QWidget.grab()` to render screenshots.
- GUI tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui`. Fixtures in `tests/gui/conftest.py`: `qapp`,
  `async_loop` (the background asyncio loop of the app) and `settings`.
- Never touch the user's real GUI settings: tests that use `QSettings` (directly or through `MainWindow`, `UiSessionStore`, the Files
  tree, ...) need the `settings` fixture, and headless runs of the app outside of pytest need `XDG_CONFIG_HOME` set to a temporary
  directory.

## Agent guidelines

- **Git**: do not stage, commit or push unless the user asks for it. Never use `git stash`, `reset` or `checkout` to compare with HEAD, use
  `git show HEAD:<file>` instead.
- **Secrets**: never print or copy plate credentials, `secrets.yaml` or MQTT passwords from config directories.
- **Config directories**: `openhasp-configs/` is the user's real configuration. Read it only for analysis (structure, counts, without
  printing values); run anything that writes on a copy in a temporary directory.
- **Lock files**: this is a Poetry project; don't commit a `uv.lock` (`uv run` creates one).
- **Real plates**: commands that deploy, clear pages or reboot affect physical devices. Do not run them against real plates unless
  the user asks for it. When the user allows measurements on a plate, never send `clearfont`, and restore the plate afterwards
  (*Restore plate* or a reboot). The `config.json` of a plate holds the WiFi and MQTT passwords: read only the keys you need
  (e.g. with `jq`), never the whole file.
- Keep `TODO.md` current: remove items when you complete them (the git history keeps them), add bugs you find but don't fix.
