# TODO

Open work and known issues. Done items are removed; the git history has them.

## 1. Bugs

None known.

- [ ] **More property values to check** (`validation/property_values.py` knows names, ranges, parts and states): `action` takes `prev`,
  `next`, `back`, `p<page>` or a JSON object of events and commands. Read how 0.7 runs a JSON action (`my_obj_set_action` and
  the event handlers) before warning about anything, so that working actions aren't reported.

## 2. Editor

- [ ] **Fact-check the preview against openHASP/LVGL.** The widgets in `gui/qt/widgets/pagelayout/openhasp_widgets/` are drawn
  with Qt from what was seen on a plate, not from the source. Defaults come from openHASP's own LVGL theme (in its source code), and
  the preview uses guesses instead: e.g. `button.py` falls back to our green `#558B2F`, `drawing.py` has `DEFAULT_ACCENT` and
  `DEFAULT_TRACK`, `base_object.py` has `_DEFAULT_RADIUS = 4`. Read the theme and object code of openHASP 0.7.0 (and the LVGL version
  it uses), list the real defaults per object, part and state (radius, border, padding, gradients, colors, fonts), fix the widgets,
  and compare them with a screenshot of the same page from a plate (`openhasp-config-manager screenshot`).
  Then try to remove `FONT_SCALE = 0.7` in `drawing.py`: it is probably a fudge factor for the difference between Qt's and LVGL's text
  rendering. Check how a font id maps to a font on the plate (family, pixel size) and use the real metrics.
- [ ] Insert template variables inside longer texts (the suggestions replace the whole value today).
- [ ] Placeholders (`"text": "%ip%"`, `gui/domain/source/placeholders.py`): `check` could warn about texts openHASP won't replace (an
  unknown `%...%`, a placeholder inside a longer text like `"IP: %ip%"`, a placeholder in the `text` of a type other than `btn`,
  `label` or `msgbox`), and the page preview could show an example value instead of `%ip%`. The editor only knows them in .jsonl
  files, not in commands of .cmd files (`p1b2.text=%ip%`).
- [ ] Preview of the new object types: objects inside a `tab` (`parentid`) and the open list of a `dropdown` are not drawn.
- [ ] Files tree: "New .jsonl file here" on a folder (adds the `run L:/<flattened name>` line to the right .cmd and checks the 30
  character limit of file names on the plate), and "Move to file" for an object.
- [ ] Changes on disk (LLM edits): merge them into a draft with changes (the draft keeps only its changed properties, so objects and
  properties that changed on only one side can combine), instead of the "Reload or Keep" banner. Show which objects changed after a reload.
- [ ] **Ordering and ids.** Z-order follows creation order on the plate, so reordering objects needs a delete and re-add of the objects
  above them. Live preview has the same issue: an object whose id changed is deleted and added again, so it ends up on top.

## 3. Parts (`!include`) in the editor

Included objects are shown and read-only (see `docs/include-directive.md`). Next:

- [ ] **Edit the `vars` of an instance in the properties panel.** An included object shows the `vars` and `for` values of its
  `!include`; changing one writes the directive (in the including file), and all objects of the instance are rendered again.
- [ ] **A mode to edit a part itself.** Open a part "as a definition": one instance is shown (chosen from the files that include it,
  or with the part's defaults), edits are written into the part file, and every instance follows.
- [ ] Copy an included object as a plain object (its values rendered with the variables of its instance). Copying is refused today,
  since the templates of the part need those variables.
- [ ] The values next to the templates in the text editor of a part are rendered with the variables of its folder only, not with
  those of an instance (`vars`, `for`, `this`, `bY` are unknown there): show them for one instance.
- [ ] A cursor in a directive could select the objects it includes in the preview (today nothing is selected).
- [ ] `vars` and `for` written before the `"!include"` key of a directive are highlighted as plain keys (the highlighter reads the
  lines from the top).
- [ ] The draft expands the directives of every file again after each edit (for the object references). Cache the instances of a
  directive while its text and its scope stay the same, if large configs make editing slow.

## 4. Composed pages (haad layouts) in the editor

The code-defined layouts (`haad/layout`, `haad/page`, `haad/plate`) already update plates incrementally: `Page.relayout()` sends only the
changed `x`/`y`/`w`/`h`, `Repeat` adds and removes single objects, ids are stable (`pXbY`), and `dump.py`/`render.py` turn a layout
into JSONL objects.

- [ ] Render a `Page` into the preview with `render.py`/`dump.py`, so the editor can show pages like the alerts page. They have no file
  to write back to, so read-only at first; the live connection shows the real runtime values.
- [ ] Layout-aware editing of `Column`/`Row`/`Panel` trees: an edit of `gap`, `padding` or `size` runs `relayout()` and sends the diff,
  the same path haad uses at runtime.

## 5. The real plate

- [ ] **Keep the display awake while Live preview is on.** The plate dims and turns its display off after the idle timeout, so the
  live preview changes can't be seen. Wake it when Live preview starts and keep it awake as long as it is on. Check this regularly
  (not once), because automations (e.g. a presence or night mode automation in haad-home) may turn the display off or dim it again
  against our intention. Read the actual state (backlight/idle state) in each check, correct it only when it differs, and stop
  when Live preview is turned off, so the plate goes back to its normal behavior.
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

## 6. Packaging and installation

The `gui` extra is done (`pip install 'openhasp-config-manager[gui]'`); AppDaemon and haad are installed by their own environments.

- [ ] Keep the API client free of CLI and GUI dependencies (click, PyQt6, …), so haad and AppDaemon projects only pull what they use.
  (`OpenHaspClient` still imports the console helpers from `openhasp_config_manager.console`.) If that is not enough, split the API
  client into its own package.
- [ ] A future TUI becomes a `tui` extra the same way.

## 7. Code structure

Found in a review of the text editor and preview work, not done yet:

- [ ] `check.py` (CLI, no Qt) imports the editor's domain from `gui/domain/` (`draft/session`, `draft/files`, `problems`,
  `gui_state.relative`). It works because `gui/domain` is Qt-free, but the layering is upside down: move the Qt-free model of the
  pages (draft, problems, page objects) out of `gui/`, e.g. to `openhasp_config_manager/pages/`.
- [ ] The geometry of some preview items is computed in their Qt classes (`HaspArcItem.angles`, `HaspGaugeItem.labels`,
  `HaspLineMeterItem.active_lines`, `drawing.fraction`): move it to `gui/domain` like `line_points.py` and `button_matrix.py`, so it is
  tested without Qt.
- [ ] `collect_gui_state` (`gui/qt/window/gui_state_collector.py`) builds the `device` part of the state file by hand: a `describe_device` in `gui_state.py`
  would make it testable without a window, like the other parts.
