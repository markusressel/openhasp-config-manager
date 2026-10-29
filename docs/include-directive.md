# Design: `!include`, computed variables and shorter object references

Status: implemented on `feature/include-directive`. This note records what was decided and why; the user documentation is in
`README.md` ("Templating", "Variables & Scoping", "Including objects").

## Motivation

The page files of a real config directory repeat themselves a lot:

1. **Templates can't create objects.** A page indicator is 25 copied objects (5 pages with 5 dots each), every "tile" of a card
   (a caption label and a value label) is copied and edited by hand.
2. **Variables can't be computed from variables.** A template in a `*.vars.yaml` value is inserted into the object as text and
   never rendered, so `card.h: "{{ device.screen.height - 40 }}"` doesn't work, and every page computes the same values again.
3. **Object references are strings.** `p3b4.w` is `"120"`, so every calculation needs `(p3b4.w | int)`, and `p3b4.x + p3b4.w`
   concatenates text.
4. **Referring to the own page is verbose.** `p{{ common.pages.printer.index }}b4.x` only to say "object 4 of this page".

Also a bug: the numeric properties were matched by prefix, so `hidden` counted as `h` and a templated `"hidden": "true"`
logged "is not a number".

## Part 1: three small changes to the templates

### Variables computed from variables

Templates in the values of `*.vars.yaml` files are rendered.

- They are rendered against the **merged variables of the path they apply to**, so an override in a device folder changes
  every value computed from it (`common.margin` overridden by a device changes `common.card.x` for that device). For a file
  in `common/` that is the variables of the file's folders merged with the variables of the device (as before), so
  computed values are per device.
- `device` (the `openhasp_config_manager.device` part of the device's `config.json`: `ip`, `screen.width`,
  `screen.height`) can be used, as in the objects.
- Variables are rendered in **dependency order**, found from the names their templates use (`a.b` depends on `a.b`, on
  everything below it, and on `a` if `a` itself is a template). A cycle is an error that names it
  (`a.x -> a.y -> a.x`), an unknown name is an error that names the variable and the name (strict, unlike the templates of
  objects, where unknown names stay as written: a variable has no later pass that could define them).
- **Values**: a value that is a single template (`"{{ common.margin * 2 }}"`) becomes the value of its expression (a
  number, a list, a mapping, ...). Any other text with templates becomes text, and text that is a number becomes a number
  (`"1{{ x }}"` with `x: 5` is `15`). Keys are not rendered.
- Objects (`p1b2`) can't be used in variables: variables are computed before the objects.
- Templates that should stay text (rare) can be escaped with `{% raw %}...{% endraw %}`.

Everything renders through `processing/template_rendering.py` (`render_variables`, `evaluate_template`). The `vars` command
prints the computed values (with the device of the path, if the path is in a device folder, or of `--device`; without a
device, the values that use `device` are printed as they are written), and so do the variable values of
the GUI (hover, values next to the text, completion), which read the variables of the draft.

### Numbers in object references

`pXbY.<property>` is a number for the numeric properties (`page`, `id`, `x`, `y`, `w`, `h`, `min`, `max`, `prev`, `next`,
`radius`, `border_width`, `pad_*`, `margin_*`, the style variants of `radius` and `border_width` with part and state digits
like `radius10`), after percentages were turned into pixels, the same way the objects are sent to the plate. So
`{{ p3b4.w - 12 }}` and `{{ p3b4.x + p3b4.w }}` work. `| int` still works on numbers, so existing files don't change.

The names are matched as whole names now (`hidden` is no longer `h`). The style variants keep working: `pad_.+` and
`margin_.+` match their part and state digits as before, `radius` and `border_width` get an optional two-digit suffix (the
only suffixes those properties have).

The conversion is done while the object references are resolved (`render_dict_recursive(convert=...)`), with the same
function the `ObjectDimensionsProcessor` uses for the output.

While the references are resolved, a template that is not resolved yet counts as an unknown variable, so a reference waits for
it. Before, `"{{ p1b2.x }}"` to an object later in the file whose `x` was a template got the text of that template (it only
worked when the reference calculated with it, which failed and was tried again).

### `this` and `bY`

- `this` is the object itself: `"w": "{{ this.h }}"` (square), `"text": "Page {{ this.page }}"`.
- `bY` is object `Y` on the page of the object, openHASP's `pXbY` without the page: `"x": "{{ b4.x + common.card.padding }}"`.

Both work like `pXbY` does: for objects later in the file, for the object itself (a property can use another property of the
same object, as `p3b45.h` inside of object 45 did before), in all files of the device, and in the GUI. They are names for
the objects in the variables (`pXbY` stays available).

- They can't be used in `page` and `id`: those say which object it is.
- `this` and `b<number>` are reserved inside of object templates: a variable with such a name is hidden there.
- For the GUI, `referenced_objects(..., page=...)` resolves `bY` to `pXbY`, so changing object 4 renders the objects that
  use `b4` again.

## Part 2: the `!include` directive

### Format

JSONL stays openHASP JSONL. Our additions are JSON objects whose key starts with `!` (like the tags of Home Assistant and
ESPHome YAML). An object is either a plain openHASP object or a directive, never a mix. The plate never sees a directive.

The only directive is `!include`, modelled on ESPHome packages:

```json
{
  "!include": "common/parts/tile.jsonl",
  "vars": {"id": 29, "caption": "Elapsed"},
  "for": {"column": [0, 1]}
}
```

- `!include`: the path of a `.jsonl` file, relative to the config directory, written as it is (no templates, so tools can
  follow it without rendering anything). It must be a file of the device: in `common/` or in the device's own folder.
- The included file (a "part") is a normal JSONL file: no header, no declaration of parameters. Its parameters are plain
  variables used in its templates. It may contain `!include` itself.
- Its objects replace the directive in place, in their order. Order matters for openHASP (z-order, and the plate sets the
  properties of an object in the order of the file).
- `vars` (optional): variables for the part, see below.
- `for` (optional): loop variable -> its values, either a JSON list or a single template whose expression is iterable
  (`"{{ range(1, 6) }}"`, `"{{ common.rooms }}"`). The part is included once per combination of the values, the cartesian
  product in the order of the keys (the first key changes slowest).

### Variables of a part

The scope of a part is merged from these layers, later ones win (dicts are merged deeply, like `VariableManager` does):

1. **The variables of the part's own location**: the `*.vars.yaml` files of the folders from the config directory down to the
   folder of the part (the normal folder scoping). These are the part's defaults.
2. **Everything the including file sees at the directive**: for a directive in a page file, the variables its objects are
   rendered with (its folders, for a file in `common/` merged with the device's variables, and `device`); for a directive in
   a part, the scope of that part's instance (so a part can pass its own parameters on, or rely on them being visible).
3. **`vars`** of the directive.
4. **The loop variables** of `for`.

Then the templates of layer 1 that are not overridden are rendered against the merged scope, so defaults can be computed
from parameters (`value_y: "{{ y + 22 }}"` next to the part).

Why the including scope wins over the defaults: a default is a default. The device or the page can override what a part uses
(e.g. `common.tile.caption.size` on a small plate), and layer 1 contains the global variables too, which must not undo the
device's overrides (the global `common.margin` of the part's chain would otherwise hide the device's `common.margin`). The
price is that a variable of the including scope with the same name as a default of the part replaces it: give parts'
defaults distinct names (e.g. below a key named after the part) if that matters.

The values of `vars` and `for` may be templates, rendered with the variables of the including scope (layer 2) and, for
`vars`, the loop variables of the combination (`"vars": {"id": "{{ 100 + dot }}"}`). A single template gives the value of its
expression, like in the variable files. A name in both `vars` and `for` is an error.

### Ids

Ids are passed as variables: the part computes the ids of its objects (`"id": "{{ id }}"`, `"id": "{{ id + 1 }}"`). The
`page` and `id` of every included object are rendered when the directive is expanded (with the scope of the instance), so
the expanded objects have their names (`p3b29`) before the objects are resolved, and can be referred to: `p3b29.x`, `b29.x`.
Included objects can refer to the objects of the including file (`b4.x`) and to each other.

Two objects with the same page and id where at least one is included is an error of the directive (the existing checks
report duplicates of plain objects).

### Pipeline

- `processing/jsonl/includes.py` parses and expands directives (`expand_includes`), using the parser of the JSONL files
  (comments, objects over several lines). It also has the checks of a directive object that need no config
  (`directive_error`), which the text editor uses as well.
- `DeviceProcessor` expands the objects of a file before the object references are resolved: the object map of
  `pXbY` contains the expanded objects, each with its own scope (`render_dict_recursive(entry_vars=...)`). An expanded
  object is rendered with the variables of its file plus its instance scope plus `this`/`bY`.
- Every expanded object has a provenance (`ObjectOrigin`): the part file, the index and line of the object in it, and the
  chain of `!include`s that led to it (file, line, index, `vars` and `for` values of each level, outermost first). Plain
  objects have an empty chain.

### Part files on deploy

A file that is only used through `!include` is not uploaded and not rendered on its own: its templates need the variables of
an instance. The rule:

- As before, a `.jsonl` file is uploaded only when a `.cmd` file runs it (or it is `hasp.pages`). A part that is not run is
  therefore never uploaded. A part that is also run by a `.cmd` is a page file too and is rendered on its own as well (with
  its defaults).
- The objects of a part are only in the object references (`pXbY`) through its instances; on its own only when the part is
  the file being rendered.
- `check` checks parts through their instances: errors in the objects of a part are reported at the part's file and line,
  with the `!include` chain.

### Errors

Reported by deploy (fails), `check` (with file and line of the directive and the chain of includes) and the GUI (at the line
of the directive in the open file):

- a key starting with `!` that is not `!include` (unknown directive),
- an object that mixes a directive with openHASP properties, or an `!include` with keys other than `vars` and `for`,
- an `!include` path that is not a string, has a template, isn't a `.jsonl` file of the device, or doesn't exist,
- `vars` or `for` that are not objects, `for` values that are not iterable, a name in `vars` and `for`,
- templates of `vars`/`for`/`page`/`id` that can't be rendered (unknown names, objects used in `vars`),
- cycles (the error names the chain of files and lines),
- id collisions of included objects.

## Part 3: the GUI

- **Preview and draft** (`PlateSession`): included objects are shown like all others, but are read-only as objects of the
  page: they can't be dragged, nudged, resized, edited, deleted, cut or duplicated. The editor explains why (like it does
  for templates) and offers to open the part file or to go to the directive. Save never writes included objects into the
  including file: the session keeps the directives of a file and only saves its plain objects and the changed `vars` and
  `for` of its directives. Undo/redo, Live preview (the included objects are sent like all others) and the Files tree keep
  working.
- **The instance of an included object** (the "Instance" group in the Properties panel): the `vars` and `for` of the
  outermost `!include` (the one in the file of the draft) are fields, a literal value or a template (`{ }`), with the
  values of the selected instance next to them. A var that is a mapping has a field for each of its values
  (`progress_bar.id`). A change (`PlateSession.set_directive_value`) writes the directive in the draft and includes it
  again: every object of its instances is rendered again (with `for`, of all instances), objects that refer to them follow,
  and instances can be added or removed. The `!include`s inside of parts are listed read-only, with a button to go to them.
  A directive in the common folder is marked "shared".
- **Part mode** (editing a part itself): "Edit the part" in the Properties panel of an included object, or in the context
  menu of a part in the Files tree, shows one instance of the part (`PlateSession.enter_part_mode`): its objects can be
  changed like plain objects (moved, nudged, edited, added, duplicated, removed), the objects around it are dimmed and
  can't be selected. A change is written into the part in the draft, and every instance follows (also those on other
  pages). A bar above the preview names the part and the instance, chooses another instance, and ends part mode ("Done");
  the changes stay in the draft until it is saved, which writes the part file. For a part in the common folder, the bar
  says how many files of which devices include it. New objects go into the part, with a `page` and an `id` template
  like those of its other objects (`{{ base + n }}`).
- **Text editor**: directive keys (`"!include"`, and `"vars"`/`"for"` of a directive) have their own token kind
  (`TokenKind.DIRECTIVE`); Ctrl+click on the path opens the part; hover explains `!include`, `vars` and `for`; the path is
  completed after `"!include": "`; the errors of the file's directives are marked in it; a directive is one object for
  folding and the object at the cursor.
- **State file** (`gui-state.json`): selected objects and problems of included objects have an `include` entry with the part
  file and line and the chain. Additive, so the schema stays 1.

## Decisions made during implementation

These were not settled beforehand. Each names the alternative that was not taken.

- **Precedence: the including scope wins over the part's defaults** (see "Variables of a part"). Alternative: defaults over
  the including scope, which would hide device overrides of global variables.
- **`vars` see the loop variables.** The task said "rendered in the including file's scope"; the loop variables are added to it
  for `vars` so that `"id": "{{ 100 + dot }}"` works. A name in both is an error instead of one silently winning.
- **A single template is the value of its expression** (in variable files and in `vars`/`for`), not its text. Alternative:
  always text, with numbers converted. The expression value keeps lists and mappings usable, and is what `for` needs anyway.
- **Paths are relative to the config directory and literal.** Alternatives: relative to the including file, or templates in the
  path. Literal paths can be followed by tools (links, completion, the deploy rule, the Files tree) without rendering.
- **A part must be a file of the device** (`common/` or the device folder), like every other file a device uses.
- **`vars` can't refer to objects.** They are rendered when the directive is expanded, before the objects are resolved, because
  `page` and `id` of the included objects depend on them. The error says how to do it instead (see "Later").
- **`page` and `id` of included objects are rendered at expansion**, with the instance scope, without objects, `this` or `bY`.
- **Objects of a part only count through their instances** in `pXbY` of other files; a part that is also run by a `.cmd` is
  rendered on its own when it is deployed (with its defaults).
- **Boolean properties stay text.** `hidden`, `enabled`, ... were numbers by accident (`hidden` matched `h`), so a templated
  `"hidden": "{{ 1 if ... else 0 }}"` was sent as `0` and is now sent as `"0"`. The plate converts every value to text when it
  reads JSONL, so this changes nothing there (a deploy uploads such files once). Alternative: a list of boolean properties that
  are converted too.
- **`for` values see only the including scope**, not `vars` (those are rendered per combination, after the values are known).
- **A directive with an error includes nothing**, the others of the file are still expanded, and every error is reported (not
  only the first). A cycle stops at the directive that closes it; the objects before it stay.
- **At most 1000 instances per directive** (`MAX_INSTANCES`): more is a mistake (openHASP has 12 pages with ids up to 254), and
  a `for` over `range(10**9)` must not hang a deploy.
- **An id collision is reported once per object that repeats the name of an object before it** (at the innermost directive
  of that object), or for the included object if only the first one is included, so a collision isn't reported twice.
- **Errors in the objects of a part** fail the deploy with the place in the part and the chain (`IncludedObjectError`); the
  errors of directives are collected first (`IncludeExpansionError`) and reported together.
- **The defaults of a part come from the YAML files of its folders.** They apply to every file in that folder, like all
  variable files do: put each part with its own defaults in a folder of its own if they shouldn't be shared.
- **Problems of included objects point at the part** (file and line of the object in the part, the chain in the message and in
  the `include` field), because the text that has to change is usually there. Errors of a directive point at the directive.

### The GUI

- **An included object belongs to the directive's file** (`component_of`, `line_of` give the including file and the line of the
  outermost `!include`), and `origin_of` says where it is written. That keeps the page, the problems and the file of the object
  consistent with the files the plate runs. `check` and the state file name the part as the place to change.
- **Copying an included object is refused** like cutting, duplicating and removing: its templates need the variables of its
  instance, so a pasted copy would not render. Alternative: copy the rendered values (see TODO.md).
- **The cursor in a directive selects nothing** in the preview (`object_of_source` skips included objects): a directive can
  include many objects on several pages.
- **The draft keeps the directives as they are.** Its objects are saved around them (the file keeps its directives and the
  plain objects in their order, new ones at its end). A directive that includes nothing (e.g. a missing part) stays too.
- **The included objects are in the undo states** like the others (they never change), so undo and redo keep them where they are.
- **Highlighting `vars` and `for` needs the lines before**: the highlighter keeps the state of the lines (how deep in brackets,
  and whether the object is a directive). `vars`/`for` before the `"!include"` key are not highlighted (rare, see TODO.md). Hover,
  folding and the object at the cursor read the whole text and don't have this limit.
- **Errors that need the config** (a missing part, a cycle, templates of `vars`) are marked from the draft (as loaded), errors of
  the text alone (`directive_error`) while typing.

### Editing the `vars` and `for` of an instance

- **The draft keeps a copy of each directive**, by its component and its index in the file, next to the objects, and the
  undo states have it. Alternative: a `DraftEntry` for each directive among the objects, which every reader of the objects
  would have had to skip. `changes()` writes the changed keys of a directive (the whole `vars` or `for` mapping) with the
  `JsonlSourceEditor`, so the rest of the file keeps its text and comments.
- **A change expands the whole file again**, with the changed directive in its place, and takes the objects of that
  directive. Objects of the same instance (same part file and index, same loop values and directives on the way) keep their
  rendered dict, with the new scope; the others are added or removed. Alternative: new objects for every instance, which
  would lose the selection and the items of the preview on every keystroke. The undo states hold the origin and scope of
  included objects, so undo gives back the instances as they were.
- **Only errors the change makes block it**: the errors of the expansion with the change that the file doesn't have
  without it (an error of another directive doesn't block it). They are shown at the field, not in the problems: the
  draft doesn't change, so it has no problem. Alternative: refuse any change while the file has an error.
- **Literal values**: a var whose value is a text stays a text (typing `12` gives `"12"`), every other value is JSON, a
  loop variable a JSON list. A template is what the `{ }` button switches to, like for properties. Alternative: JSON for
  all values, which makes every text need quotes.
- **Fields apply while typing**, like the property fields, and the panel isn't made again for it (only the values that
  changed are updated). An edit that adds or removes objects reloads the page; the edited object stays selected if it is
  still included, and its field gets the focus back.
- **The draft writes its directives in the order of the file** (also those that include nothing), so a directive is never
  further down in the draft than in the file. The expansion finds the line of a directive in the file by its place, which
  raised an `IndexError` for a directive that includes nothing after objects were added.
- **No cache per directive.** On the user's config an edit of `vars` takes as long as an edit of a property (about 0.45 s,
  most of it the object references of every file, see TODO.md); checking the change takes milliseconds.
- **Names of `vars` can't be added or removed in the panel** (the session takes any mapping): see TODO.md.

### Part mode

- **The draft keeps a copy of every part** its files include (`PartDraft`: the part's objects with a uid each), loaded with
  the draft, and the expansion takes the parts from it (`DeviceProcessor.set_draft_parts`). The included objects of a part
  object share its source, so an edit in one instance is the edit of the part. Alternative: load a part only when part mode
  starts, which would need a second way to render the instances when the draft is undone past it.
- **Instances are known by their directives**: a key of the file and index of the outermost `!include`, the uid of the part
  object of each `!include` inside of parts, and the loop values. Objects whose key stays keep their rendered dict when
  the draft includes the parts again. Alternative: the lines of the directives, which change with every edit of a part.
- **One routine includes everything again** (`_reinclude`): after an edit of a part, of `vars` or `for`, and after a save.
  It renders the objects whose part or scope changed, and keeps the others. Alternative: a routine per kind of change.
- **Only the objects of the part itself can be changed** in part mode, not those of the parts it includes: those are
  edited in part mode of their own part. Alternative: write each change into the part it comes from, which would make a
  change in one place change other parts unseen.
- **"Use pixels for x/y" asks first** in part mode: the pixels of the instance that is shown are written into the part, so
  every instance gets the same x and y.
- **Copying and pasting are refused** in part mode: the objects of a part need the variables of their instance, and pasted
  objects have no templates for their `page` and `id`. Duplicating works (the copy gets the next id template).
- **Part mode is not in the undo history**: undo changes the objects, not the mode. Undoing the addition of a part's only
  objects ends nothing; the bar then names no instance. Alternative: undo steps for entering and leaving part mode.
- **Part mode survives a reload** (a save, a change on disk) if the instance is still included, found by its description
  (file, line and loop values of its directives); otherwise it ends.
- **A part that is also a page file of the device** (run by the `.cmd`) can't be edited in part mode: its objects are
  plain objects of that file too, and one edit would have to go to both.
- **The defaults of a part are cached** in the `DeviceProcessor` (they only change with the files): including the parts
  again after an edit took 0.45 s on the user's config, 0.36 s with the cache. An edit in part mode takes 0.4 to 0.8 s there
  (see TODO.md).

## Later

- `!extends`: an object that takes the properties of a part object and overrides some of them.
- Editing a part on its own, with its defaults instead of the variables of an instance (part mode shows an instance).
- Templates in the `!include` path.
- `vars` values that refer to objects (`"x": "{{ b4.x + 10 }}"`): they would have to be rendered per object, after the
  objects; today pass the id of the object and refer to it in the part, e.g. `{{ b{{ anchor }}.x }}`.
