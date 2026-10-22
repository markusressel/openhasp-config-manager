# TODO

Open work and known issues. Done items are removed; the git history has them.

## 1. Bugs

- [ ] `ad`: `OpenHaspClient.set_gui_config` is called without `await` in `ad/plate/deployment.py` (`deploy_config`, which is not async
  itself, called from `ad/plate/screen.py`) and `ad/plate/__init__.py` (`set_gui_config`), so the GUI config is never sent.
- [ ] Templates that refer to other objects (`{{ p1b5.x }}`) are rendered with the objects as they are on disk, not with the draft.
- [ ] A template that is not valid yet is lost when the property panel is rebuilt (e.g. after moving the object).
- [ ] Checking a template for a numeric property that renders to text logs a traceback from `ObjectDimensionsProcessor` (it logs
  failed conversions with `LOGGER.exception` and `print`); log one line instead.

## 2. Editor

- [ ] Insert template variables inside longer texts (the suggestions replace the whole value today).
- [ ] Files tree: "New .jsonl file here" on a folder (adds the `run L:/<flattened name>` line to the right .cmd and checks the 30
  character limit of file names on the plate), and "Move to file" for an object.
- [ ] **One edit model.** Make the editor emit small edit operations (`add(obj)`, `remove(id)`, `set(id, property, value)`,
  `move/resize(id, rect)`) on the `PlateSession` draft. The preview, the JSONL view, the dirty state and Live preview all subscribe to
  the same operations.
- [ ] Undo/redo, built on the edit model.
- [ ] **Ordering and ids.** Z-order follows creation order on the plate, so reordering objects needs a delete and re-add of the objects
  above them. Live preview has the same issue: an object whose id changed is deleted and added again, so it ends up on top.

## 3. Composed pages (haad layouts) in the editor

The code-defined layouts (`haad/layout`, `haad/page`, `haad/plate`) already update plates incrementally: `Page.relayout()` sends only the
changed `x`/`y`/`w`/`h`, `Repeat` adds and removes single objects, ids are stable (`pXbY`), and `dump.py`/`render.py` turn a layout
into JSONL objects.

- [ ] Render a `Page` into the preview with `render.py`/`dump.py`, so the editor can show pages like the alerts page. They have no file
  to write back to, so read-only at first; the live connection shows the real runtime values.
- [ ] Layout-aware editing of `Column`/`Row`/`Panel` trees: an edit of `gap`, `padding` or `size` runs `relayout()` and sends the diff,
  the same path haad uses at runtime.

## 4. The real plate

- [ ] Verify Restore plate: whether `clearpage all` also clears page 0, and whether `run /pages.jsonl`, `page`, `run /boot.cmd`,
  `run /online.cmd` rebuild the plate like a restart (the docs don't give the startup order).
- [ ] Verify what the runtime and Live preview rely on: `delete` cascading to children, a single JSONL add onto a shown page, and the
  `x`/`y`/`w`/`h` commands.
- [ ] Optional: a preview that follows the real plate (its state topics: touch events, values), where clicking can trigger the same action
  as touching the plate.
- [ ] Postponed: compare the draft with the plate. openHASP 0.7.0 has no command to list objects, dump a page or read a whole object
  back, only single property getters (`command/p1b2.text` with an empty payload answers on `state/p1b2`, see
  `OpenHaspClient.get_object_property`). So only the objects the draft knows can be compared, one round trip per property; objects that
  exist only on the plate stay invisible. Probing every id and screenshots were rejected.

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
