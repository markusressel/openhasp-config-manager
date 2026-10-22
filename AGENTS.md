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
- Dependencies: `poetry install` (add `--with ui` for the GUI). A `.venv` in the repository root is used by the commands below.
- Run the CLI: `.venv/bin/openhasp-config-manager --help`, e.g. `gui -c ./openhasp-configs`.

## Commands

| Task                         | Command                                                     |
|------------------------------|-------------------------------------------------------------|
| Tests                        | `make test` (= `cd tests && poetry run pytest`)             |
| Single test                  | `cd tests && ../.venv/bin/pytest manager_analyze_test.py -k <name>` |
| haad integration tests       | `make test-haad` (runs in `../haad`'s uv environment, 100 % coverage required) |
| Lint (CI runs `ruff check .`) | `make lint`                                                |
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
- `OpenHaspClient` is async: every call must be awaited. A missing `await` fails silently (the coroutine never runs), which once broke
  deploy, upload and screenshots.

## GUI editor

- **Draft**: `PlateSession` (`gui/domain/plate_session.py`) keeps every object twice: rendered (shown in the preview) and as written in its
  file, with its templates. Change objects through the session (`set_source_value`, `add_object`, `paste_objects`, ...), never by
  mutating the rendered dicts: Save patches only the changed source properties back into the files.
- **Templates are never replaced implicitly.** Objects whose `x`/`y` is a template or a percentage can't be dragged or nudged; the
  editor explains why, and "Use pixels for x/y" replaces them only when the user asks. Keep this for new edit operations.
- **Files**: new objects go into the target file chosen in the Files tree (`gui/domain/file_tree.py` follows the folder structure of
  `README.md`), by default the device's own file, never a shared `common/` file unless the device has none: saving a shared file changes
  every device that loads it.
- **Plate actions** (names and tooltips agreed with the user): *Live preview* sends the draft to the plate while editing (nothing is stored
  on it), *Restore plate* rebuilds the pages from the files on the plate like a restart, *Deploy* uploads the saved files. *Revert*
  discards the draft; *Undo* is reserved for undo/redo.
- **Remembered state**: what should survive a restart for a config directory or a device goes into `UiSession`/`DeviceSession`
  (`gui/domain/ui_session.py`) as a dataclass field with a default, then `ui_session.save()` (`gui/qt/ui_session_store.py`). App-wide
  preferences (window geometry, theme, view toggles) are plain `QSettings` keys.
- **Preview controls** float inside the preview (`PagePreviewWidget.add_overlay`); `fit_to_view` keeps their rows free, so the plate is
  never covered. Messages about an object go next to it (`show_message`), errors also to the status bar (`OperationStatus.failed`).

## Testing

- Add or adjust tests with every behavioural change. `pytest-asyncio` runs in auto mode (`tests/pytest.ini`).
- `tests/haad` and `tests/ad` are skipped unless haad or AppDaemon are installed (`tests/conftest.py`). `tests/haad/README.md`
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
  the user asks for it.
- Keep `TODO.md` current: tick items off when you complete them.
