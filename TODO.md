# TODO

Open work and known issues. Done items are removed; the git history has them.

## 1. Bugs

- [ ] Large files in the code editor (measured with 25,000 lines; typing itself is fast, `gui/domain/source/structure.py`):
  - the issue check (`update_issues`, 300 ms after typing stops) blocks the UI for about 4 s: it tokenizes the whole text three
    times. Make it incremental like `TextStructure`, or run it off the UI thread.
  - opening the file (`set_text`) takes about 20 s, most of it in highlighting and the issue check.

## 2. Editor

- [ ] Compare the preview with the plate: the defaults in `gui/domain/default_theme.py` were measured on a plate, not read from
  openHASP's theme source. Check them against the theme code of openHASP 0.7 (and its LVGL version) per object, part and state, and
  compare a page with a screenshot of it from a plate (`openhasp-config-manager screenshot`).
- [ ] Placeholders in commands of .cmd files (`p1b2.text=%ip%`): `check` (`placeholder_problems` in
  `gui/domain/source/placeholders.py`) and the editor only know them in .jsonl files.
- [ ] Children of an `obj` container (`parentid` of an object that isn't a tab) are drawn at plate coordinates instead of relative
  to their parent, and not clipped to it. Objects on a tab are (`PagePreviewWidget._nest_items`); extend it to the other parents.
- [ ] An object on a tab that isn't shown (`val` of the tabview) is invisible, so selecting it (e.g. from the text editor) shows no
  outline in the preview. Switch to its tab, or outline where it would be.
- [ ] "Move to file" for an object.
- [ ] Files tree: drag and drop to move files and folders (the context menu has "Move to…"), and moving fonts (`.ttf`): the pages
  name fonts without `L:/`, so their references are not changed and moving a folder with a font is refused.
- [ ] Changes on disk (LLM edits): merge them into a draft with changes (the draft keeps only its changed properties, so objects and
  properties that changed on only one side can combine), instead of the "Reload or Keep" banner. Show which objects changed after a reload.
- [ ] **Ordering and ids.** Z-order follows creation order on the plate, so reordering objects needs a delete and re-add of the objects
  above them. Live preview has the same issue: an object whose id changed is deleted and added again, so it ends up on top.

## 3. Parts (`!include`) in the editor

Included objects are shown and read-only, except in a part tab (see `docs/include-directive.md` and
`docs/tabs-and-shared-drafts.md`). Next:

- [ ] The part tab of a part that no page includes (a part on its own) shows templates that refer to objects of its page (`b4.w` of
  a card) unresolved: offer to show it on a page of the device, with the objects of that page in its references.
- [ ] Change the `vars` and `for` of an `!include` inside of a part in a part tab (the "Instance" group is hidden there; only the
  outermost `!include` of a page file can be changed today).
- [ ] Copy an included object as a plain object (its values rendered with the variables of its instance). Copying is refused today,
  since the templates of the part need those variables.
- [ ] The values next to the templates in the text editor of a part are rendered with the variables of its folder only, not with
  those of an instance (`vars`, `for`, `this`, `bY` are unknown there): show them for one instance.
- [ ] A cursor in a directive could select the objects it includes in the preview (today nothing is selected).
- [ ] The draft expands the directives of every file again after each edit (for the object references). Cache the instances of a
  directive while its text and its scope stay the same, if large configs make editing slow. Measured on the user's config
  (`touch_down_1`): about 0.45 s per edit of a property or of `vars`, most of it in `jsonl_template_variables` (expanding and
  copying the variables of every file). An edit in a part tab takes 0.4 to 0.8 s there. With several devices open this adds up: an
  edit of a shared file renders every open device that shows it at once (`PlateSession._sync`); render the devices in the
  background tabs debounced, or when their Live preview or tab needs them (`docs/tabs-and-shared-drafts.md`, Part 1).

## 4. Tabs and the shared draft (`docs/tabs-and-shared-drafts.md`)

Left over from the implementation:

- [ ] A file that is a page file of one device and a part included by another one has two drafts in the
  `ConfigDraft`: in `files` and in `parts`). Editing both and saving fails with `SaveConflictError`.
- [ ] The tab of a part that no page includes has a draft of its own (placeholder vars), so Save in another tab doesn't write it,
  and it may hold a second copy of a part the shared draft has too. Share the `ConfigDraft` with it.
- [ ] Restoring the tabs on start doesn't restore their page and zoom, and part tabs come back after the other tabs of their device
  instead of at their place.
- [ ] The Plates panel shows the page of a plate only after it changed pages once (the plate sends `state/page` only on a change):
  ask for it when the connection is made (probably `command/page` with an empty payload; check that the plate answers).

## 5. Composed pages (haad layouts) in the editor

The code-defined layouts (`haad/layout`, `haad/page`, `haad/plate`) already update plates incrementally: `Page.relayout()` sends only the
changed `x`/`y`/`w`/`h`, `Repeat` adds and removes single objects, ids are stable (`pXbY`), and `dump.py`/`render.py` turn a layout
into JSONL objects.

- [ ] Render a `Page` into the preview with `render.py`/`dump.py`, so the editor can show pages like the alerts page. They have no file
  to write back to, so read-only at first; the live connection shows the real runtime values.
- [ ] Layout-aware editing of `Column`/`Row`/`Panel` trees: an edit of `gap`, `padding` or `size` runs `relayout()` and sends the diff,
  the same path haad uses at runtime.

## 6. The real plate

- [ ] **Keep the display awake while Live preview is on.** The plate dims and turns its display off after the idle timeout, so the
  live preview changes can't be seen. Wake it when Live preview starts and keep it awake as long as it is on. Check this regularly
  (not once), because automations (e.g. a presence or night mode automation in haad-home) may turn the display off or dim it again
  against our intention. Read the actual state (backlight/idle state) in each check, correct it only when it differs, and stop
  when Live preview is turned off, so the plate goes back to its normal behavior.
- [ ] Verify Restore plate: whether `clearpage all` also clears page 0, and whether `run /pages.jsonl`, `page`, `run /boot.cmd`,
  `run /online.cmd` rebuild the plate like a restart (the docs don't give the startup order).
- [ ] Verify what the runtime and Live preview rely on: `delete` cascading to children, a single JSONL add onto a shown page, and the
  `x`/`y`/`w`/`h` commands.

## 7. Code structure

- [ ] `check.py` (CLI, no Qt) imports the editor's domain from `gui/domain/` (`draft/session`, `draft/files`, `problems`,
  `gui_state.relative`). It works because `gui/domain` is Qt-free, but the layering is upside down: move the Qt-free model of the
  pages (draft, problems, page objects) out of `gui/`, into `openhasp_config_manager/model/` (the Qt-free model that
  code-defined pages use, `docs/config-model-api.md`).

## 8. The config model (`docs/config-model-api.md`)

The first slice (`ConfigModel.load()`, `variables()`, `expand_part()`, `render_part()`, the `Part` leaf) is done. Next, as pages need it:

- [ ] `Part(..., bind={id: Bound(...)})` for bound properties of a part's objects.
- [ ] A `Part` in a `Repeat` (`ids=<count>`, `vars` as a callable of the first id; decision 1 of the note).
- [ ] `files()`, `entries()`, `part()` and `render_file()`, and the GUI and `check` on them.
- [ ] A part that moves (a node before it collapses): render it again with the new `area` and send the moved objects, instead of
  raising.
- [ ] A plate start analyzes the config twice (`ConfigModel.load()` and the `DeploymentController`): share it if a large config makes
  starts slow.
- [ ] haad-home's tests build a plate controller by hand (`tests/controllers/openhasp/conftest.py`): export a testing helper (like
  `FakePlate` in `tests/haad`) that declares and renders pages without a connection.
