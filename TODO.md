# TODO

Open work and known issues. Done items are removed; the git history has them.

## 1. Bugs

None known.

## 2. Editor

- [ ] Insert template variables inside longer texts (the suggestions replace the whole value today).
- [ ] Object types: the editor can add and draw 20 of the 22 openHASP objects. Missing:
  `cpicker`, `msgbox`. Objects of these types are not drawn in the preview today. Each needs a widget in the preview
  (`openhasp_widgets/`, registered in `registry.py`) and an entry in `page_objects.WIDGET_TYPES` (the picker).
- [ ] Files tree: "New .jsonl file here" on a folder (adds the `run L:/<flattened name>` line to the right .cmd and checks the 30
  character limit of file names on the plate), and "Move to file" for an object.
- [ ] **One edit model.** Make the editor emit small edit operations (`add(obj)`, `remove(id)`, `set(id, property, value)`,
  `move/resize(id, rect)`) on the `PlateSession` draft. The preview, the JSONL view, the dirty state and Live preview all subscribe to
  the same operations.
- [ ] Undo/redo, built on the edit model.
- [ ] Changes on disk (LLM edits): merge them into a draft with changes (the draft keeps only its changed properties, so objects and
  properties that changed on only one side can combine), instead of the "Reload or Keep" banner. Show which objects changed after a reload.
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

The `gui` extra is done (`pip install 'openhasp-config-manager[gui]'`); AppDaemon and haad are installed by their own environments.

- [ ] Keep the API client free of CLI and GUI dependencies (click, PyQt6, …), so haad and AppDaemon projects only pull what they use.
  (`OpenHaspClient` still imports the console helpers from `openhasp_config_manager.console`.) If that is not enough, split the API
  client into its own package.
- [ ] A future TUI becomes a `tui` extra the same way.
