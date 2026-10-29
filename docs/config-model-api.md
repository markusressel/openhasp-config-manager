# Design: the config as an API for code-defined pages

Status: the first slice, steps 1 and 2, is implemented (`openhasp_config_manager/model/`, `Part` in
`openhasp_config_manager/haad/layout/components.py`, see "Decisions made during implementation"). Step 3 and "Later" are not.

## Motivation

Code-defined pages (`haad/layout`, e.g. the alerts page of haad-home) build again by hand what the config directory already has:

- the header of every code page (`MarkusCodePageController` in haad-home: a `Panel` with the time, the title and items on the right) is
  `common/parts/header/header.jsonl`,
- `light_row()` (`haad-home/controllers/openhasp/layout/parts.py`) is `common/parts/light/light.jsonl`,
- the navbar of a code-defined page 0 (`NavbarPage`) is `common/navigation_bar.jsonl`,
- haad-home's `theme.py` reads `theme.yaml` and `common/common.vars.yaml` as plain YAML: a computed variable
  (`common.card.y: "{{ ... }}"`) comes back as its template, and the variables of the plate's device (`device.vars.yaml`) are missing.

The config already knows how to compute all of this (variables per device, `!include` with `vars` and `for`, object references, the theme
of each object type), but only as internals of the deployment and the GUI.

Goal: code-defined pages use the parts, variables and theme of the config, rendered exactly like a deployment renders them, so both kinds
of pages look the same and change together. E.g. the alerts page includes the header part instead of rebuilding it.

## Non-goals

- **The deployment doesn't change.** JSONL pages stay files on flash, deployed with `openhasp-config-manager deploy` (or haad's
  `PlateDeployment`). Nothing of this API writes to the config directory or the plate's flash.
- haad doesn't render and push the JSONL pages of the config (see "Later").
- No editing through the API: `PlateSession` stays the model of the GUI.

## Part 1: the model (openhasp-config-manager, Qt-free)

A new public module, `openhasp_config_manager.model`. It is the only supported surface for other code. It is built on the code a
deployment uses (`ConfigManager`, `DeviceProcessor`, `expand_includes`, the JSONL processors), so it can't render differently.

```python
class ConfigModel:
    """The config directory, as one device sees it."""

    @staticmethod
    def load(config_dir: Path, device: str) -> "ConfigModel": ...

    device: Device  # name, screen (after rotation), config.json without its secrets

    def variables(self, path: str = "common") -> Mapping[str, Any]:
        """The computed variables of a path for this device, like `vars -p <path> -d <device>`, with `device`."""

    def files(self) -> List[ConfigFile]:
        """The files the device has: kind (cmd, page, part, variables, image, font), path, and who runs or includes them."""

    def entries(self, path: str) -> List[Entry]:
        """The objects and `!include`s of a JSONL file as written: `ObjectEntry(source, line)`, `IncludeEntry(path, vars, for, line)`."""

    def part(self, path: str) -> Part:
        """A part: its entries, its defaults (the variable files of its folders) and its parameters (the names its templates
        use that no variable file defines, e.g. `tile.caption`)."""

    def render_part(
        self, path: str, *, page: int, vars: Mapping[str, Any], objects: Mapping[int, Mapping] = {}
    ) -> List[RenderedObject]:
        """The objects of one instance of a part, as a deployment would send them: templates rendered, percentages in pixels,
        theme applied, validated. `objects`: other objects of the page (by id), for the references of the part (`b4.x`)."""

    def render_file(self, path: str) -> List[RenderedObject]:
        """The objects of a JSONL file of the device, the same as `generate` writes."""


@dataclass(frozen=True)
class RenderedObject:
    jsonl: Mapping[str, Any]  # page, id, obj, ...
    origin: ObjectOrigin  # the part file and line, the chain of includes (see include-directive.md)
```

- Variables and parts are rendered with the variables of the device, as on a deployment: a part in `common/` sees the variables of the
  device folder too.
- The instance scope of `render_part` is the one of an `!include` (include-directive.md, "Variables of a part"): the part's defaults, the
  variables of `common/` for the device, `page_index`/`vars` given here.
- Errors are the ones of `check` and a deployment (`IncludeExpansionError`, `IncludedObjectError`, `TemplateRenderError`), raised: fail
  fast, the caller can't render half a part.
- `load` reads the files once. After a change of the config, load it again (haad: restart, as for code changes).
- The GUI and `check` move onto this module over time; this is the move of the Qt-free model out of `gui/` (TODO.md §6).

## Part 2: parts in code-defined layouts (`openhasp_config_manager.haad.layout`)

A plate controller with a `config_dir` (`OpenHaspControllerParams.config_dir` in haad-home) loads a `ConfigModel` for its device at start.
Layouts use it through a new leaf:

```python
Part("common/parts/header/header.jsonl", vars={"header": {"title": "Alerts"}})
```

- **Placement**: a `Part` is a leaf in the layout: it takes its `size=`/`weight=` in a `Row`/`Column` like any other, and gets a rectangle.
  The part is rendered with that rectangle as `area` (`area.x`, `area.y`, `area.w`, `area.h`) and the page as `page_index`. Its objects
  are where the part puts them: parts written for code layouts place themselves in `area`; the parts of today place themselves from
  `common.*` and other objects (`b4`), and work as they are (a `Part` with `at=` and no size takes no space, like any leaf with `at=`).
- **References**: `bY` in a part is an object of the code page (its rendered layout object) or of the part itself. Parts are rendered
  after the layout pass, so the objects of the page have their rectangles; the other leaves can't refer to the objects of a part.
- **Ids**: the part computes its ids from its variables, as in the config. The `page` and `id` of included objects are rendered before
  the objects (include-directive.md, "Ids"), so the page knows them before it allocates ids for its other leaves, and skips them.
  Duplicates raise (`JsonlObjectValidator`, as for every rendered page).
- **Binding**: the objects of a part are owned objects of the page. `part.obj(id)` is the typed `ObjectController` of one of them
  (`LabelObjectController` for a `label`), from `register_objects()` on, like `.obj` of a leaf; bind it with the existing methods, or with
  `Part(..., bind={21: Bound(...)})` for properties.
- **Theme**: the objects get the theme of the config through `render_part` (`theme.obj.*`), the other leaves of the page get
  `Theme` as today. haad-home builds its `Theme` and the constants of `theme.py` from `ConfigModel.variables()` instead of reading YAML,
  so both are the same values, including computed ones and the overrides of the device.
- **Pushing**: unchanged (§5 of `haad/layout/README.md`): the part's objects are in the page's rendered JSONL, pushed with it, dumped with
  it, and restored after a reconnect.

### Example: the header of the alerts page

```python
class MarkusCodePageController(PageController):
    async def build_layout(self) -> Page:
        with Page(padding=Padding(bottom=NAVBAR_HEIGHT)) as page:
            # the bar, the time and the title, like every JSONL page
            Part("common/parts/header/bar.jsonl", at=Rect(0, 0, 0, 0))
            self.header = Part("common/parts/header/header.jsonl", vars={"header": {"title": self.title}}, size=HEADER_HEIGHT)
            with Column(padding=MARGIN, gap=8):
                await self.build_content()
        return page

    async def register_objects(self):
        # the time label of the part (id.time)
        await self.header.obj(10).bind(entity=TIME_ENTITY)
```

## First slice

1. `ConfigModel.load()` and `variables()`; haad-home's `theme.py` on it.
2. `render_part()` and the `Part` leaf, with `part.obj(id)`; the header of the code pages from `common/parts/header/`.
3. Then, as needed: `bind=`, `Part` in `Repeat` (see the questions), `files()`/`entries()`/`render_file()`.

## Decisions

1. **Parts in `Repeat`**: an item of a `Repeat` is created at runtime, and its leaves get the lowest free ids of the page. A part
   computes its ids from its variables, so a fixed id would collide with the second item. A `Part` in an item therefore takes
   `ids=<count>`: the page reserves that many consecutive free ids for it, and `vars` is a callable that gets the first one
   (`Part(path, ids=3, vars=lambda first: {"light": {"id": first}})`). The ids of the part's objects must be inside that block,
   or rendering raises. Not part of the first slice.
2. **Uses by code**: `check` can't know which parts and variables code uses, so they are not counted. A part that only code
   uses is not run by any `.cmd` and so not uploaded; its variables may be reported as "Not used".
3. **The device of a plate**: a plate uses the device folder of its name. Plates without a `config_dir` can't use parts.
4. **Module**: `openhasp_config_manager.model`: a model of the config directory that is read, rendered, and later written
   back.

## Decisions made during implementation

What the note above didn't settle, as it was decided for the first slice, with the alternative that was not taken:

1. **How `render_part` reuses the pipeline**: it renders a virtual file `common/<code page N>.jsonl` of the device, which has the
   given `objects` and one `{"!include": path, "vars": {...vars, "page_index": N}}`, through the same
   `DeviceProcessor` as `generate` (`DeviceProcessor.render_sources`), and keeps the included objects. So the instance scope, the
   object references, `ObjectDimensionsProcessor`, `ObjectThemeProcessor` and `JsonlObjectValidator` are the deployment's, and
   a test compares a rendered part with the `generate` output of the same `!include`. Not taken: a second entry point into
   `expand_includes` with its own scope and reference handling, which could drift from the deployment.
2. **The other objects of the page**: the objects that the device's own files have on page N are not visible to the part
   (`replaced_page`): the code page replaces them, and `b4` must be the code page's `b4`. The objects of the other pages stay
   visible, as on a deployment. Not taken: all objects of the device, which would let `b4` silently resolve to an object of a
   JSONL page that the code page replaces.
3. **`page_index` is the page's**: `vars` can't set `page_index` (raises `ValueError`), and an object of the part on another page,
   or a page object in `objects` with another page or id than its key, raises. Not taken: letting a part place objects on other
   pages, which a code page can't push.
4. **`expand_part`** (not in the note): `ConfigModel.expand_part(path, *, page, vars) -> List[PartObject]` gives the page, id and
   type (`obj`) of every object of an instance, from the include expansion alone. The page needs the ids (to skip them) and the
   types (for the object controllers) when it is mounted, before the layout pass that gives the rectangles `render_part`
   needs. Not taken: rendering the part twice, once with a dummy `area`, which breaks for parts whose ids or types depend on it.
5. **`describe(origin)`**: `ConfigModel.describe(origin) -> str` names where an object comes from
   (`common/parts/header/header.jsonl:3 > common/parts/header/label.jsonl:2`) without the virtual file. It is the declaration of
   the part's objects in the layout dumps and errors.
6. **`Device` has no credentials**: `model.device` is a frozen `Device(name, path, ip, screen, gui, hasp)`, with the screen after
   rotation. Not taken: the `Config` of `config.json` with blanked secrets, which still hands out a type with password fields.
7. **The theme**: the part's objects are rendered with the config's theme (`theme.obj.*`, by `ObjectThemeProcessor`), and
   `render_page` applies only `ObjectDimensionsProcessor` to them, not the page's `Theme`, so the config's theme is not applied
   twice and the page's can't override it.
8. **Binding**: `LabelObjectController.bind_text(entity=, attribute=, get_state=, text=, trigger=)` instead of the note's
   `part.obj(10).bind(entity=...)`, which would collide with the existing `ObjectController.bind()` (the binding to the plate).
   It takes the arguments of `Label(...)`, can only be called once and before the label is initialized (raises otherwise). `bind=`
   stays for later.
9. **`part.obj(id, cls)`**: the optional `cls` checks the type (`TypeError`) and types the result, e.g.
   `part.obj(10, LabelObjectController)`. An unknown id raises `ValueError`, a call before the mount `RuntimeError`.
10. **A part can't move**: it is rendered for the rectangle it has when the page is mounted. A later layout pass that moves it
    (a node before it collapsing through a bound `hidden`) raises. Not taken: rendering it again and sending the moved objects,
    which needs the part's objects to be re-rendered with the new `area` and is left for when a page needs it.
11. **Where a part can't be**: in a `Repeat` (decision 1 above, later), in a `Panel` (the part's objects are placed relative to the
    screen, not to an object) and in `Page(external=True)` (its objects are pushed). Each raises when the `Part` is created.
12. **The screen**: the plate's screen must be the screen of the device in the config (after rotation), or the part raises when
    the page is mounted: `area` and `common.*` would be computed for another screen.
13. **Templates in `vars` and `objects`**: they are rendered like the `vars` of an `!include` in a file (with the device's
    variables), because the virtual file is such a file. Not taken: passing them as literal values.
14. **Loading**: `OpenHaspController.initialize()` loads the model (`self.config_model`) for its `config_dir` before it reads
    `plate_config`, so a plate config can be built from the variables (haad-home's `MarkusStyle.of(self.config_model).theme`), and
    passes it to the `PlateController` (`plate.config_model`). The `DeploymentController` still analyzes the config separately, so
    a start reads the config twice. Not taken: sharing one `ConfigManager` between them, which would tie the model to the
    deployment's output directory.
15. **The "layout" of a part that ignores `area`**: the header parts place themselves from `common.header.*`. haad-home puts them
    in a `Stack` with a fixed `size=` (the header height), together with a `Row` for the items on the right of the bar, instead of
    `at=Rect(0, 0, 0, 0)` and a second `size=` as in the example above.
16. **haad-home's style**: `theme.py` has a `MarkusStyle` per plate (`MarkusStyle.of(model)`, `MarkusStyled.style` on pages)
    instead of module constants, because the variables are those of the plate's device (e.g. `wt32sc01plus_2` overrides
    `common.margin`). Its pages call `super().register_objects()` first, which binds the time of the header.
17. **`PlateController.declare_objects(page)`** is public (was `_declare_objects`): haad-home's tests declare and render a page
    without starting the plate controller, which would connect to the plate.

## Later

- haad renders and pushes the JSONL pages of the config from the model (no deployment for page changes, `vars` computed at runtime).
- Writing a model back to files (what `PlateSession` does for the GUI).
