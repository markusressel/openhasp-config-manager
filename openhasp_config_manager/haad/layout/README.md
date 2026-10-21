# Code-defined plate layouts (design)

Status: **in progress**. The checklists in §7 track what is implemented; open questions are collected in [QUESTIONS.md](QUESTIONS.md).

This document describes how a haad project (e.g. `haad-home`) can define the complete layout of an openHASP plate in Python, and have the
`OpenHaspController` push it to the device at runtime. No `.jsonl` files, no Jinja templates, no `openhasp-config-manager deploy` step.

The existing workflow (layout in `.jsonl`, deployed to flash, wired in `register_objects()` by `obj_id`) is not replaced. Both workflows are
equally supported, with the same features, and can be mixed on one plate. Breaking changes to the current API are fine where they make
things simpler: the `haad` package of openhasp-config-manager is not released yet, and all its usages (in `haad-home`) are refactored together
with it.

---

## 1. Today

A single control, e.g. the desk light switch on the "Markus" page, lives in three places:

1. `openhasp-configs/common/page/mk/content.jsonl`: geometry and style, with a hand-picked `"id": 22`, theme values pulled in via
   `{{ theme.obj.switch.* }}`, and positions copied from other objects via `{{ p{{ common.pages.markus.index }}b20.y }}`.
2. `openhasp-configs/devices/<plate>/device.vars.yaml` and `boot.cmd`: which page index the page gets on which plate, and which files run.
3. `haad-home/controllers/openhasp/page/markus.py`: `await self.add_switch(obj_id=22, entity_id=...)`.

Pain points:

- **Ids are a manual contract** between the JSONL and the Python code. Nothing checks that `obj_id=22` in Python is actually the switch at id 22 in
  the JSONL (see the `TODO: find a way to get rid of manual ID settings` in `mk/content.jsonl`).
- **Two deployments**: a layout change needs a `deploy` to flash *and* a haad restart; forgetting one gives a plate that silently does not match the code.
- **Templating in strings**: reuse (header bar on every page, navbar, "icon + label + switch" rows) happens through Jinja and copy-paste
  (`common/page/header.jsonl` repeats the same object for pages 1-9). Python has functions, classes and loops for this.
- **The device needs a `config_dir`**: `DeploymentController` runs `ConfigManager.analyze()` on the config directory to find the `Device`
  (IP, MQTT, HTTP credentials, screen size), even when nothing is deployed from it.

## 2. Goals and non-goals

Goals:

- One declaration per object: geometry, style and behaviour (entity binding, callbacks) in one call.
- The same declarative `with` style as the haad dashboards (`haad.ui`, `DashboardController.build_ui()`).
- Automatic object ids. Explicit ids remain possible.
- Plain Python for reuse: functions, base classes, loops, constants. No string templating.
- A plate can be defined without any `openhasp-configs` directory: connection settings come from `haad.yaml`.
- The layout is (re-)pushed automatically whenever the plate comes online, so a reboot or a power cut never leaves an empty screen.
- Both workflows are first-class: layouts from JSONL on flash and layouts from code, declared with a `with` tree or with explicit calls.
  None of them is the "real" API with the others as fallbacks; every binding feature works with all of them.
- The behaviour of today's plates is pinned by tests *before* the first change (§7, phase 0), so refactorings, breaking ones included, can't
  change what a plate does by accident.
- The library stays agnostic: no notion of headers, titles or navbars. Opinionated page frames belong to the project (e.g. `haad-home`).

Non-goals (for the first version):

- A WYSIWYG editor. The Qt GUI in `openhasp_config_manager/gui` stays a JSONL tool (it can preview code-defined pages through their layout dumps, see §6.1).
- Fonts and images on flash (`L:/...`). Code-defined objects can reference them (`"text_font": 32`, `"src": "L:/bg.png"`), but they are
  not uploaded by haad: they still come from the existing deployment. The docstrings of `add_image`, `add_object` and `Theme` say so.
- An automatic flex/grid layout engine on the device. Layout helpers compute absolute coordinates in Python.
- Partial updates of a page layout. A changed layout means: clear the page, push it again. Property updates at runtime are unchanged
  (`ObjectController.set_object_properties()`).

## 3. Core idea

Two independent choices per page:

- **Where the layout lives**: on the plate's flash (JSONL, deployed with openhasp-config-manager: *external* objects), or in code (pushed by
  haad at runtime: *owned* objects).
- **How the page declares its objects**: as a `with` tree in `build_layout()`, or with explicit `add_*` calls in `register_objects()`.

|                         | Layout in code (owned)                                     | Layout on flash (external)                               |
|-------------------------|------------------------------------------------------------|----------------------------------------------------------|
| **`with` tree**         | `Page()`, containers, leaves with sizes and properties     | `Page(external=True)`, a flat list of leaves with `obj_id` |
| **explicit calls**      | `await self.add_switch(rect=..., props=..., entity=...)`   | `await self.add_switch(obj_id=22, entity=...)` (today)   |

```python
# with tree, layout in code
async def build_layout(self) -> Page:
    with Page() as page:
        with Row(gap=8):
            Label(text="Desk", weight=2, text_font=32)
            Switch(entity=desk.entity, weight=1)
    return page

# with tree, layout on flash
async def build_layout(self) -> Page:
    with Page(external=True) as page:
        Switch(obj_id=22, entity=desk.entity)
    return page

# explicit calls, layout in code
async def register_objects(self):
    await self.add_switch(rect=Rect(x=200, y=60, w=100, h=48), entity=desk.entity)

# explicit calls, layout on flash
async def register_objects(self):
    await self.add_switch(obj_id=22, entity=desk.entity)
```

The `with` tree follows the same pattern as `DashboardController.build_ui()` in haad (`haad/ui`, used by
`haad-home/controllers/dashboard.py`): components created inside a `with` block attach themselves to it. Unlike `build_ui()`,
`build_layout()` is `async`, like every other page hook (see 4.2).

All four combinations end in the same place: one `ObjectController` per object, created by the `add_*` methods (the tree calls them while
mounting), with the same bindings (`entity=`, `get_state=`, `trigger=`, `Bound` properties, callbacks) and the same handle methods
(`set_text()`, `set_hidden()`, ...). A feature added to one combination is added to all of them.

## 4. API

### 4.1 Plate: connection and screen

A code-defined plate does not need `config_dir`/`output_dir`. Its connection settings come from the controller's section in `haad.yaml`
(`self.controller_config()`, supports `!secret`, raises if missing):

```yaml
controllers:
  wt32sc01plus_3:
    host: 192.168.5.172          # openHASP web UI / HTTP API
    mqtt_name: wt32sc01plus_3    # the plate's hasp/<mqtt_name>/... topic prefix
    http_user: admin
    http_password: !secret openhasp_http_password
    # optional; default: the broker from haad.yaml's `mqtt` section
    # mqtt: { host: ..., port: 1883, user: ..., password: !secret ... }
```

What is *not* a secret or a connection detail goes into code, in `PlateConfig`:

```python
@dataclass(frozen=True)
class Screen:
    width: int
    height: int


@dataclass(frozen=True)
class GuiDefaults:
    idle1: int  # seconds until "short" idle
    idle2: int  # seconds until "long" idle


class PlateConfig:
    def __init__(
        self,
        screen: Screen | None = None,            # required for code-defined objects
        theme: Theme = Theme(),
        gui: GuiDefaults | None = None,          # replaces device.config.gui from config.json
        screen_brightness_default: ScreenState = ...,
        screen_brightness_short_idle: ScreenState = ...,
        screen_brightness_long_idle: ScreenState = ...,
    ): ...
```

`OpenHaspControllerParams` (in `haad-home`) gets `config_dir: Path | None = None`. The plate's device comes from one of two sources:

| `config_dir`   | Source of `Device` (IP, MQTT, HTTP, screen, gui defaults)                         |
|----------------|-----------------------------------------------------------------------------------|
| set (today)    | `ConfigManager.analyze()` of the config directory, unchanged.                      |
| `None` (new)   | `controller_config()` + `PlateConfig`. A small factory builds an in-memory `Device` |

The factory builds the `Device`/`Config` dataclasses that `OpenHaspClient` already expects, so the client does not change. `DeploymentController`
is only created when `config_dir` is set; `PlateController.update_plate_behavior()` and `ScreenController` read the gui defaults through one
accessor (`PlateController.gui_defaults`) instead of `deployment_controller.device.config.gui`.

### 4.2 Pages: `build_layout()` and `register_objects()`

`PageController` gets one new hook:

```python
class PageController:
    async def build_layout(self) -> Page | None:
        """Declares the page's objects as a component tree, owned or (with Page(external=True)) external. Default: None."""
        return None

    async def register_objects(self):
        """Objects declared with add_*, react_to(), plate behaviours, ... Default: nothing."""
```

**Everything is async.** All page hooks are `async`, `build_layout()` included, even though most layouts await nothing. Mixing sync and
async hooks on the same class has caused confusion before, so the rule is: async unless there is a strong reason not to be. The same goes
for reusable parts (4.6). The only synchronous pieces are the component constructors (`Row(...)`, `Label(...)`): Python has no async
`__init__`, and they do no I/O.

`register_objects()` no longer raises `NotImplementedError` by default (breaking, but simpler: a page may use only one of the two hooks).
Instead, the plate raises when a page declares no objects at all, so a forgotten override still fails at startup.

`build_layout()` runs before `register_objects()`, so `register_objects()` can use the handles of tree objects (see 4.4). A page that uses
a tree typically splits like this:

- `build_layout()`: everything visible, with its bindings (`entity=`, `text=`, `on_click=`, bound properties).
- `register_objects()`: behaviour that is not about one object: plate behaviours (`request_plate_behavior`, `go_to_this_page`,
  `plate.wakeup()`), images pushed from URLs, values computed and set in code.

`build_layout()` may await (e.g. an overridable `async def get_media_player_app()`), but the tree is built once per haad process. Entity
*state* does not change the tree: state goes into bindings (`text=`, `entity=`, `Bound`) or property changes (`.obj.set_hidden(...)`).

Nesting uses a `ContextVar` (4.10), which is per asyncio task. Await helpers one after another; don't run them concurrently
(`asyncio.gather`, `create_task`): the components would still attach to the right parent, but the order of siblings, and with it the
layout and the auto ids, would depend on scheduling.

### 4.3 Layout containers

Containers are virtual: they only compute positions and cost no object id on the device. Positions are computed in Python and sent as
absolute pixel values; openHASP's own layout features are not used.

| Container               | Places its children                                                                                         |
|-------------------------|-------------------------------------------------------------------------------------------------------------|
| `Page(padding=...)`     | Root of a page tree. Its area is the full screen minus `padding` (e.g. the height of a page-0 navbar).      |
| `Column(gap, padding)`  | Top to bottom.                                                                                              |
| `Row(gap, padding)`     | Left to right.                                                                                              |
| `Grid(columns, gap, padding)` | In equal cells, row by row. The number of rows follows from the number of children.                   |
| `Stack(padding)`        | All children in the same area, on top of each other (e.g. an image with a label over it).                   |
| `Spacer()`              | Nothing: takes space in a `Row`/`Column`.                                                                   |
| `Panel(gap, padding, direction, **props)` | Like `Row`/`Column`, but it *is* an openHASP `obj` (background, border, radius); its children get `parentid` and positions relative to it. |

Sizing, for every component (containers and leaves) inside a `Row`/`Column`:

- `size=`: a fixed length along the main axis, in pixels (`48`) or a percentage of the parent (`"25%"`).
- `weight=` (default `1`): a share of the space that is left after fixed sizes and gaps.
- Cross axis: the child fills it.
- Pixel rounding: the weighted shares are rounded cumulatively, so they add up exactly and neighbouring objects never have gaps or
  overlaps from rounding. Fixed sizes that don't fit raise.
- `Page` places its children like a `Column`.

In a `Page(external=True)` tree, containers, `size=`, `weight=` and `at=` raise: the layout is on flash, and code that looks like a layout
but isn't one would be misleading.

For pixel-exact placement inside a tree, any component takes `at=Rect(...)`: it is placed at that rectangle relative to its parent and takes
no space in the flow. `Rect` (with its helpers like `rows()`/`cols()`, see 4.8) is the same type `add_*` takes.

### 4.4 Objects

One leaf class per openHASP object type, with the same binding arguments as the matching `add_*` method, plus sizing:

| Leaf                                       | Mounted with               | openHASP `obj` |
|--------------------------------------------|----------------------------|----------------|
| `Label(text=..., entity=..., attribute=..., get_state=...)` | `add_label`   | `label`        |
| `Button(text=..., on_click=...)`           | `add_button`               | `btn`          |
| `SceneButton(scene=..., text=...)`         | `add_scene_button`         | `btn`          |
| `Switch(entity=..., get_state=...)`        | `add_switch`               | `switch`       |
| `Slider(entity=..., on_changed=..., on_released=...)` | `add_slider`    | `slider`       |
| `Bar(entity=..., get_state=..., transform_value=...)` | `add_bar`       | `bar`          |
| `Checkbox(...)`                            | `add_checkbox`             | `checkbox`     |
| `Image(...)`                               | `add_image`                | `img`          |
| `Obj(type="arc", ...)`                     | `add_object`               | any            |

- **Properties**: all other keyword arguments are openHASP properties and passed through as-is, like `UIComponent` treats extra
  kwargs as props: `Label(text="Desk", align="left", text_font=32, text_color="#FFFFFF")`. The API never blocks a property it doesn't know.
  `add_*` takes the same as `props={...}`. For owned objects they are part of the pushed JSONL; for external objects they are set when the
  object is bound and on every `sync()` (e.g. `mode="scroll"` instead of today's `set_mode("scroll")` right after `add_label`).
- **Entities**: `entity=` accepts an `HAEntity` wrapper, an entity id, or a list of them (like `entity=` in `haad.ui`). The `add_*` methods
  get the same `entity=` argument instead of today's `entity_id=` (breaking, all usages are refactored).
- **`text=`** on `Label`/`Button` is a `str` (static) or a `Callable[[Any], str]` (converter of the bound state, today's meaning).
- **Callbacks** are the same for leaves and `add_*`. `on_click` becomes `async () -> None` (breaking: today `(topic, payload)`, which no
  usage reads, and `ButtonObjectController` only forwards `up` events anyway). So `Button(on_click=x1.pause_printing)` and
  `add_button(obj_id=50, on_click=self.plate.reboot)` work without wrapper functions.
- **`trigger=`** (leaves and `add_*`): when a value comes from `get_state`, the refresh trigger can be any haad `Trigger`,
  e.g. `Trigger.Time.every(interval=timedelta(seconds=1))`, instead of binding a clock sensor like `TIME_SECOND_ENTITY` only to get a tick.
  `entity=` stays the shortcut for an entity trigger.
- **Bound properties**: any property can follow another entity, see 4.4.1.
- **Handles**: a leaf has a typed `.obj` property, the `ObjectController` it was mounted as (`Label.obj: LabelObjectController`), the
  same object `add_label` returns. It is
  available from `register_objects()` on; reading it earlier raises. Keep a handle by assigning the leaf:
  `self.co2_text = Label(...)` in `build_layout()`, then `await self.co2_text.obj.set_border_width(3)` later.
- **Ids**: `obj_id=` pins the id, otherwise ids are allocated (see 4.8). Required for every leaf of a `Page(external=True)` tree.
- **Fonts and images** (`text_font`, `src="L:/..."`) must already be on the plate's flash: haad does not upload them.
- **Object methods behave the same for owned and external objects**. E.g. `.obj.push_image(image, width, height)` keeps its explicit
  size: a default taken from the layout would only exist for owned objects, and external ones would behave differently.
- Creating a leaf outside a `with Page()` block raises, instead of creating an object that silently never reaches the plate.

#### 4.4.1 Bound properties

Several pages change a property of one object when *another* entity changes: the CO2 label gets a border above 1000 ppm, the printer's
temperature labels change colour while heating and hide while the target is unavailable. Today each of these is a separate
`react_to(immediately=True)` callback. These callbacks are not registered with `StateUpdater`, so after a plate reboot or reconnect the
property stays wrong until the entity changes again.

Any property, as a leaf kwarg or in `add_*(props={...})`, for owned and external objects alike, can be a `Bound` instead of a value:

```python
@dataclass(frozen=True)
class Bound[T]:
    trigger: HAEntity | str | Trigger
    convert: Callable[[Any], T] | None = None              # gets the entity state; None for unknown/unavailable
    get_state: Callable[[], Awaitable[Any]] | None = None  # value source instead of the entity state, like get_state on leaves
```

Binding the object registers one `react_to(immediately=True)` and one `StateUpdater` entry per bound property, so every `sync()` restores it. A
`Bound` on a time trigger without `get_state` raises (there is no entity state to convert). The pushed JSONL leaves bound properties out;
the first sync sets them.

### 4.5 Style: `Theme` and props

```python
@dataclass(frozen=True)
class Theme:
    background_color: str = "#000000"
    # per openHASP object type ("btn", "label", "switch", "bar", ...): defaults applied to every object of that type,
    # unless the object sets the property itself (same rule as ObjectThemeProcessor for theme.obj.* today)
    obj: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
```

`haad-home` defines its theme once, as a Python constant that replaces `openhasp-configs/theme.yaml`:

```python
MARKUS_THEME = Theme(
    obj={
        "btn": {"bg_color": "#558B2F", "bg_color02": "#33691E", "bg_color04": "#666666", "radius": 20, "border_width": 0},
        "switch": {"radius00": 20, "bg_color": "#666666", "bg_color10": "#558B2F", "bg_color20": "#FFFFFF", ...},
        "label": {"text_color": "#FFFFFF"},
    },
)
```

Precedence, from lowest to highest: theme defaults, the object type's own defaults (e.g. a switch starts `enabled: false` until its entity
state is known), the leaf's typed arguments (static `text`, ...), the leaf's property kwargs. A style shared by a few objects is a plain dict:
`Label(text="Desk", **BIG_TEXT)`.

### 4.6 Reuse: components as async functions

Because components attach themselves to the enclosing `with` block, a reusable part is an async function that creates components (async
for the same reason as the hooks, even when it awaits nothing). It returns the handles the caller needs:

```python
async def light_row(name: str, entity: HAEntity | str | list[str]) -> Switch:
    with Row(gap=4):
        Label(text=Icon.LIGHTBULB, align="center", text_font=32)
        Label(text=name, weight=2, text_font=32)
        return Switch(entity=entity, weight=2)


# in a build_layout():
with Column(gap=8):
    await light_row("Desk", desk.entity)
```

Icons come from `openhasp_client.icons.IntegratedIcon` (`IntegratedIcon.LIGHTBULB.unicode`), so pages don't contain raw escape
sequences (whether `IntegratedIcon` should format as its code point: QUESTIONS.md 15). A part that needs
arguments for its outer container (e.g. `size=`) takes them and passes them on.

### 4.7 Page frames, global objects and navigation

The library has no notion of a header, a title or a navbar: a page is whatever its `build_layout()` returns. What the library offers:

- **Page 0** (objects shown on every page) is a regular page with `index=0` and its own `build_layout()`.
- **Reserved space**: `Page(padding=...)` keeps an area free, e.g. for page-0 objects at the bottom of the screen.
- **Page cycling**: today `navigation_bar.jsonl` sets `prev`/`next` on `p<first>b0`/`p<last>b0` from `common.navbar.first_page`/`last_page`
  in `device.vars.yaml`. With code-defined pages the plate knows all page indices, so after pushing the layout it sets `prev` and `next`
  of every page (except page 0) to its neighbours, wrapping around. That overrides the flash values, so a code-defined page added to a
  JSONL plate is reachable by swiping without a deploy. A plate can switch this off with `PlateConfig(wrap_navigation=False)`.

A frame that repeats on every page (header bar, title, clock) is a project decision, so it lives in the project, as a base page class with
template methods. In `haad-home` that is `MarkusPageController`, which already exists for `register_header_clock()`. It replaces both
`register_header_clock()` and `common/page/header.jsonl`; the navbar becomes a page-0 page in `haad-home`:

```python
# haad-home/controllers/openhasp/page/__init__.py (opinionated, not part of the library)
class MarkusPageController(PageController):
    title: str

    async def build_layout(self) -> Page:
        with Page(padding=Padding(bottom=NAVBAR_HEIGHT)) as page:
            with Column():
                with Panel(direction="row", size=HEADER_HEIGHT, padding=Padding(x=6), **HEADER_STYLE):
                    Label(entity=TIME_ENTITY, align="left")
                    Label(text=self.title, weight=2, align="center")
                    with Row():
                        await self.build_header_items()
                with Column(padding=8, weight=1):
                    await self.build_content()
        return page

    async def build_header_items(self) -> None:
        """Right side of the header bar. Default: empty."""

    async def build_content(self) -> None:
        raise NotImplementedError()
```

### 4.8 Explicit calls: `Rect` and `add_*`

`Rect` is the geometry type of both declaration styles: `add_*(rect=...)` takes it, and so does `at=` in a tree.

```python
type Length = int | str  # pixels, or a percentage of the parent like "20%"


@dataclass(frozen=True)
class Rect:
    x: Length
    y: Length
    w: Length
    h: Length

    def resolve(self, width: int, height: int) -> Rect: ...  # percentages to pixels, in a parent of that size
    # the helpers need pixel Rects (resolve() first) and return pixel Rects
    def inset(self, all: int = 0, *, x: int = 0, y: int = 0) -> Rect: ...
    def rows(self, *weights: float, gap: int = 0) -> list[Rect]: ...
    def cols(self, *weights: float, gap: int = 0) -> list[Rect]: ...
    def grid(self, rows: int, cols: int, gap: int = 0) -> list[list[Rect]]: ...
```

Percentages work like in JSONL today (`ObjectDimensionsProcessor`): `x`/`w` relative to the parent's width, `y`/`h` to its height.
`Row`/`Column`/`Grid` use the same functions as `rows()`/`cols()`/`grid()`, so both layers place objects identically.

All `add_*` methods get the same arguments. Example for the switch:

```python
async def add_switch(
    self,
    obj_id: int | None = None,          # optional for owned objects: auto-assigned
    entity: HAEntity | str | list[HAEntity | str] | None = None,  # was entity_id: str
    get_state: Callable[[], Awaitable[Any]] | None = None,
    trigger: Trigger | None = None,
    *,
    rect: Rect | None = None,           # set: the object is owned by haad and pushed to the plate
    props: Mapping[str, Any | Bound] | None = None,
    parent: ObjectController | None = None,  # openHASP parentid; rect is then relative to the parent
) -> SwitchObjectController: ...
```

- `add_label(text=...)` accepts `str | Callable[[Any], str]`, `add_button(on_click=...)` becomes optional (a button without it is a styled box),
  and a new generic `add_object(obj: str, rect: Rect, props=...)` covers openHASP types without a wrapper (`obj`, `arc`, `line`, `roller`, ...).
- Calling an `add_*` method without `rect` and without `obj_id` raises `ValueError` (fail fast: an external object needs an id).
- `ObjectController` gets a read-only `owned: bool` and the rendered `jsonl: dict` (empty for external objects).

**Id allocation**: owned objects get ids per page in declaration order (tree order, then `register_objects()` order), starting at 1 (id 0 is
the page itself). Explicit ids are reserved first, auto ids skip them. More than 254 objects on one page raise. Ids do not need to be stable
across haad restarts: every start clears the owned pages once before the first push (§5.2), and `StateUpdater` registrations are rebuilt on
every start. Explicit ids are only needed to freeze a page into a JSONL file (§6.1).

### 4.9 Full examples

A page using only the library API, no project base class:

```python
class SwitchGridPage(PageController):
    """One switch per entity, in a grid that fills the screen."""

    def __init__(self, *args, entities: list[HAEntity], **kwargs):
        super().__init__(*args, **kwargs)
        self.entities = entities

    async def build_layout(self) -> Page:
        with Page() as page:
            with Grid(columns=2, gap=8, padding=8):
                for entity in self.entities:
                    with Column(gap=4):
                        Label(entity=entity, attribute="friendly_name", align="center")
                        Switch(entity=entity)
        return page
```

The "Markus" page from `haad-home`, on top of its `MarkusPageController` (4.7). Everything that was in `mk/content.jsonl`,
`mk/_header.jsonl` and `mk/vars.yaml` is in this file:

```python
class MarkusPage(MarkusPageController):
    title = "Markus"

    async def build_header_items(self):
        self.co2_sensor: Co2Sensor = Registry.markus_room_controller.co2_sensors[0]
        Label(
            entity=self.co2_sensor.carbon_dioxide, text=lambda x: f"{int(x)}ppm", align="right",
            border_width=Bound(self.co2_sensor.carbon_dioxide, lambda x: 3 if x is not None and float(x) > 1000 else 0),
        )
        Label(entity=self.co2_sensor.temperature, text=lambda x: f"{float(x)}°C", align="right")

    async def build_content(self):
        room = Registry.markus_room_controller
        with Row(gap=8):
            with Column(gap=8, weight=3):
                await light_row("Desk", room._desk.entity)
                await light_row("Light Bar", room._desk_strip.entity_ids)
                Spacer(weight=2)
            with Column(gap=8, weight=1):
                for scene, text in [("work", "Work"), ("bedtime", "Bedtime"), ("sleeping", "Sleeping")]:
                    SceneButton(scene=scene, text=text)

    async def register_objects(self):
        # behaviour, not layout: wake the plate while the CO2 level is high
        await self.controller.react_to(
            action=self._on_co2_state_changed,
            trigger=self.co2_sensor.carbon_dioxide.entity_id,
            immediately=True,
        )

    async def _on_co2_state_changed(self):
        co2_level = await self.co2_sensor.carbon_dioxide()
        if co2_level is not None and co2_level > 1000:
            await self.plate.wakeup()
```

And the plate, without any `openhasp-configs` directory:

```python
@haad_controller(
    registry_name="wt32sc01plus_3",
    params=OpenHaspControllerParams(name="wt32sc01plus_3", config_dir=None),
)
class WT32SC01Plus3(MarkusOpenHaspController):
    @property
    def plate_config(self) -> PlateConfig:
        return PlateConfig(
            screen=Screen(width=320, height=480),
            theme=MARKUS_THEME,
            gui=GuiDefaults(idle1=30, idle2=120),
        )

    async def setup_plate(self):
        await self.setup_navbar()  # page 0
        await self.setup_markus_page(index=1)
        await self.setup_media_page(index=2)
        await self.setup_about_page(index=3)
```

### 4.10 Shared nesting mechanism with `haad.ui`

`haad/ui/core.py` implements the nesting with a `ContextVar` (`_active_parent`): `__enter__` sets the component as the active parent,
`__exit__` resets it, and `__init__` appends the new component to the active parent's `children`.

The openHASP components do **not** subclass `UIComponent`: its contract is the `haad-web` frontend (`get_state()`, `to_dict()`, string ids,
`visible`/`disabled` conditions), none of which applies here. Only the nesting is shared. It moves from `UIComponent` into a small base class
in haad, `haad/util/composition.py`:

```python
class Composable:
    """A node that attaches itself to the enclosing `with` block of the same family."""
    _active_parent: ClassVar[ContextVar["Composable | None"]]  # one ContextVar per family

    children: list[Self]

    def __init__(self): ...                 # append to _active_parent.get(), if any
    def __enter__(self) -> Self: ...        # set self as active parent
    def __exit__(self, *exc) -> None: ...   # reset the token, also on exceptions
```

`UIComponent` and the openHASP `LayoutNode` both extend it, each family with its own `ContextVar`. That way a `Label` created inside a
dashboard `with Card()` (or the other way round) does not end up in the wrong tree. `haad.ui` behaves exactly as before; this is a pure
refactoring of `haad/ui/core.py`, with its own tests. The hooks are not shared: `build_ui()` stays as it is in haad.

### 4.11 Today's usage patterns in the tree

Every pattern of the pages in `haad-home/controllers/openhasp/page/` has a place in the tree (and, the same way, in explicit `add_*` calls):

| Pattern                                                              | Seen in                       | In the tree                                                        |
|----------------------------------------------------------------------|-------------------------------|--------------------------------------------------------------------|
| Label bound to an entity or attribute, with a converter              | markus, bathroom, livingroom  | `Label(entity=..., attribute=..., text=lambda x: ...)`             |
| Label switching icons by state                                       | bathroom                      | same, the converter returns the `IntegratedIcon`                   |
| Entity only as trigger, value from `get_state`, also lists of entities | printer, media              | `Label(entity=..., get_state=...)`, as today                       |
| Value refreshed every second (`TIME_SECOND_ENTITY`, `Trigger.Time.every`) | printer, media           | `trigger=Trigger.Time.every(...)`                                  |
| Static text via a dummy binding (`text=lambda x: "Elapsed:"`)        | printer                       | `Label(text="Elapsed:")`                                           |
| Property set once after creation (`set_mode("scroll")`)              | printer                       | property kwarg `mode="scroll"`                                     |
| Switch toggling an entity (or a list of entities)                    | markus, bathroom              | `Switch(entity=...)`                                               |
| Scene button, button with any action                                 | markus, about, printer        | `SceneButton(scene=...)`, `Button(on_click=x1.pause_printing)`     |
| Property following another entity (border, colour, hidden)           | markus, printer               | `Bound(...)` (4.4.1)                                               |
| Object without binding, updated in code; images from URLs            | media, printer                | leaf without binding, `.obj` in `register_objects()`               |
| Plate behaviours, page switching, per-page state                     | media, printer                | unchanged, in `register_objects()` and page attributes             |
| Page reused with another data source (`get_media_player_app()`)      | media                         | subclassing; `build_layout()` can await the overridable hook       |

Two examples. The bathroom page (on `MarkusPageController`):

```python
class BathroomPage(MarkusPageController):
    title = "Bad"

    async def build_header_items(self):
        climate = Registry.bathroom_controller._climate_control_bathroom.climate
        Label(entity=climate, attribute="current_temperature", text=lambda x: f"{float(x)}°C", align="right")

    async def build_content(self):
        bath = Registry.bathroom_controller
        with Column(gap=8):
            with Row(size=64, gap=4):
                Label(entity=bath._mirror_light.entity, text_font=32, align="center",
                      text=lambda x: IntegratedIcon.LIGHTBULB_ON if x == STATE_ON else IntegratedIcon.LIGHTBULB)
                Label(text="Mirror", weight=2, text_font=32)
                Switch(entity=bath._mirror_light.entity, weight=2)
            Label(entity=bath._presence_radar.presence, size=48, text_font=32,
                  text=lambda x: IntegratedIcon.RUN if x == STATE_ON else " ")
            Spacer()
```

Parts of the printer page: bound colours, a reusable row with a ticking value, a bar with a label on top, a camera image updated in code:

```python
EVERY_SECOND = Trigger.Time.every(interval=timedelta(seconds=1))


async def stat_row(name: str, value: Callable[[], Awaitable[str]], trigger: HAEntity | Trigger) -> None:
    with Row(size=32):
        Label(text=name)
        Label(get_state=value, trigger=trigger, weight=2, align="right")


class A3DPrinterPage(MarkusPageController):
    title = "3D Printer"

    async def build_header_items(self):
        x1 = Registry.x1carbon
        Label(
            entity=x1.nozzle_temperature_sensor, text=lambda x: f"T: {int(float(x))}°C", align="right",
            hidden=Bound(x1.nozzle_target_temperature_number, lambda t: t is None),
            text_color=Bound(x1.nozzle_target_temperature_number,
                             lambda t: HtmlColor.FireBrick.value if t is not None and float(t) > 0 else HtmlColor.White.value),
        )
        ...  # bed temperature: the same with the bed entities

    async def build_content(self):
        x1 = Registry.x1carbon
        with Column(gap=4):
            Label(entity=x1.current_stage_sensor, get_state=self._status_text, mode="scroll", size=32)
            await stat_row("Elapsed:", self._elapsed, EVERY_SECOND)
            await stat_row("Remaining:", self._remaining, EVERY_SECOND)
            await stat_row("ETA:", self._eta, x1.remaining_time_sensor)
            with Stack(size=40):
                Bar(entity=x1.print_progress_sensor, transform_value=to_int)
                Label(get_state=self._progress_text, trigger=x1.current_layer_sensor, align="center")
            with Row(weight=1, gap=8):
                self.camera = Image()
                Button(text="Pause", on_click=x1.pause_printing, size="35%")

    async def register_objects(self):
        x1 = Registry.x1carbon
        await self.controller.react_to(action=self._on_stage_changed, trigger=x1.current_stage_sensor.entity_id, immediately=True)
        await self.controller.react_to(action=self._update_camera, trigger=x1.current_layer_sensor.entity_id, immediately=True)

    async def _update_camera(self):
        url = await Registry.x1carbon.get_cover_image_url()
        await self.camera.obj.set_hidden(url is None)
        if url is not None:
            await self.camera.obj.push_image(image=url, width=108, height=192)
```

`_status_text`, `_elapsed`, `_remaining`, `_eta`, `_progress_text` and `_on_stage_changed` are today's inner functions as methods. Today the
bed label sets `bg_color` while heating but `text_color` otherwise; whether that is intended is decided separately (phase 0 pins it as is).

The same page with explicit calls and its layout still on flash keeps today's shape, with the new arguments where they help:

```python
async def register_objects(self):
    x1 = Registry.x1carbon
    await self.add_label(
        obj_id=12, entity=x1.nozzle_temperature_sensor, text=lambda x: f"T: {int(float(x))}°C",
        props={"text_color": Bound(x1.nozzle_target_temperature_number,
                                   lambda t: HtmlColor.FireBrick.value if t is not None and float(t) > 0 else HtmlColor.White.value)},
    )
    await self.add_label(obj_id=26, entity=x1.current_stage_sensor, get_state=self._status_text, props={"mode": "scroll"})
    await self.add_label(obj_id=30, get_state=self._elapsed, trigger=EVERY_SECOND)
    await self.add_button(obj_id=20, on_click=x1.pause_printing)
```

## 5. Rendering and pushing

### 5.1 Pipeline

`PlateController.init()` today runs `register_objects()` and then `initialize_objects()` for every page. The tree is built and mounted before
`register_objects()`, and the push goes right before `initialize_objects()`, because that syncs state into the objects and so needs them to
exist:

```
setup_plate()                      # pages are added
for page, one after the other:
    build_layout()                 # async: the component tree
    mount()                        # layout pass (tree -> Rects), then one add_*(rect=...) per leaf, in tree order
    register_objects()             # imperative additions; .obj handles of the tree are available
    render_layout(page)            # theme + percentages + validation, in memory (+ layout dump)
    push_layout(page)              # if the page is owned: clear it, send its JSONL
    initialize_objects()           # bind: listeners, react_to, StateUpdater.register + sync, props, Bound
set_navigation()                   # prev/next of the first/last page
```

One page after the other (not one step for all pages, then the next step) keeps the traffic of plates without owned pages exactly as
it was. Until its page is pushed, an owned object doesn't exist on the plate (and the push clears the page): property changes in
`register_objects()` (`await self.co2.obj.set_border_width(3)`) are therefore merged into its pushed JSONL instead of being sent.

`render_layout()` reuses the existing processors so JSONL files and code produce identical objects: `ObjectThemeProcessor` for theme defaults
(fed from `Theme.obj`), `ObjectDimensionsProcessor` for percentages and value types, and `JsonlObjectValidator` for duplicate `page`/`id` pairs
and required keys. Errors raise before anything is sent to the plate.

The push bypasses `ObjectController.set_object_properties()`, so its de-duplication cache (`_last_properties`) doesn't know the pushed values.
Every push is therefore followed by `PlateController.sync()`, which already clears all caches before syncing (today's behaviour on `LWT
online`). Bound properties (4.4.1) are not part of the pushed JSONL; the sync sets them.

### 5.2 When the layout is pushed

Layouts are sent over MQTT (`hasp/<name>/command/jsonl`). Objects created this way live in RAM only: the plate loses them on every reboot and
then runs its `boot.cmd` from flash. Per the [openHASP docs](https://www.openhasp.com/0.7.0/commands/global/), `jsonl` *creates new objects or
updates the properties of an existing object*, and on an update the `obj` property is ignored. That allows two kinds of push:

| When                                                                 | Push                                    | Why                                                                                                                    |
|----------------------------------------------------------------------|-----------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| Initial plate setup after a haad start (`__failsafe_plate_setup`)    | `clearpage <index>`, then all objects   | The plate may still show a layout from the previous haad run: removed objects, removed properties, or an id that now has another `obj` type (which an update would ignore). |
| Every `LWT` `online` message (`setup_online_state_listener()`)       | `clearpage <index>`, then all objects   | The plate either rebooted or only reconnected. After a reboot, its `boot.cmd` may have put objects from flash on the page (e.g. a header repeated on pages 1-9), and an update can't change an object's type. A reconnect makes the page flicker once. |

Both are followed by today's state `sync()`. Nothing is rendered again on `LWT online`: the rendered layout from the start is kept in memory.
A code change to a layout still needs a haad restart (haad has no hot reload); the restart clears and pushes the new layout.

This also covers dev takeover: production does not run any controller while a dev instance is the leader. When the dev instance (maybe with a
layout under development) disconnects, production boots again and its initial clear-and-push restores the production layout.

### 5.3 Ownership of pages

- A page with at least one owned object is an **owned page**. Only owned pages are cleared and pushed.
- A page with only external objects (from `Page(external=True)` or `add_*(obj_id=...)` without `rect`) is never cleared or pushed.
- **Mixing owned and external objects on one page is not allowed**, because the initial clear would delete the external (flash) objects. It
  raises in `render_layout()`. Mixing on one *plate* is fine: page 1 from JSONL, page 2 from code. Mixing the declaration styles on one page
  is fine as well, as long as all objects are owned or all are external.
- Page 0 is cleared and pushed like any other owned page. A plate that keeps its navbar in JSONL simply has no owned page-0 objects.

### 5.4 Transport

One `jsonl` payload may contain several objects, one per line, but openHASP cuts payloads off at its 2 kB MQTT buffer. `push_layout()` therefore
packs as many whole lines as fit into 2 kB (minus a safety margin) into each message, instead of one message per object like the Qt GUI. An
object that does not fit into a payload on its own raises in `render_layout()`.

The Qt GUI pauses 100 ms between messages to not overwhelm the device. `push_layout()` sends the (few, 2 kB) messages one after the
other without a pause for now: haad has no sleep on its runtime clock, and a pause through `schedule()` would deadlock inside the plate
setup, which itself runs in a scheduled callback (QUESTIONS.md 22).

On the initial push the current page is visibly built up. If that turns out to be distracting, `push_layout()` can push the start page last and
switch to it only when done.

## 6. Mixing with the JSONL workflow

| Plate                         | `config_dir` | Pages                                        |
|-------------------------------|--------------|----------------------------------------------|
| layouts on flash              | set          | all external (JSONL on flash)                |
| migration in progress         | set          | some external, some owned                    |
| fully code-defined            | `None`       | all owned; flash only holds fonts/images     |

Moving a page between the two happens page by page, in both directions. From flash to code: give the page a layout (a `Page()` tree or
`rect=` on its `add_*` calls), remove its `run L:/...` line from the device's `boot.cmd`, deploy once, done. For a fully code-defined plate, `boot.cmd` can be reduced to `clearpage all`.

### 6.1 Freezing a code-defined page into a JSONL file

Code-defined layouts make iterating fast: change the code, restart haad, the plate shows it. A page can be moved to flash at any time, e.g.
so it shows right after a reboot instead of after haad's next push, or to continue in the Qt editor.

**Layout dumps.** On every render, the running instance writes the rendered owned objects of each page to
`<project>/openhasp-configs.output/haad/<plate>/p<index>.jsonl` (configurable via `OpenHaspControllerParams.layout_dump_dir`, `None` turns it
off). The file is valid openHASP JSONL *and* readable by `openhasp-config-manager`:

- explicit `page` and `id` on every object, coordinates in pixels, theme defaults already applied (no `{{ ... }}`);
- one `//` comment per object with its declaration site and binding, e.g. `// markus.py:31 Switch(entity=light.desk)`.

Because the dumps are plain files in the `openhasp-configs` format, the Qt page layout editor can open them for a preview of code-defined
pages, and the dev instance's dump (under `openhasp-configs.output/haad/`, next to the `logs/<instance_type>/` convention) can be diffed against
production's.

**Freezing a page** is then a manual, three-step change, done once per page:

1. Copy the dump into the config repository, e.g. `openhasp-configs/common/page/mk/content.jsonl`, and add its `run L:/...` line to the plate's
   `boot.cmd` (or the page's `page.cmd`). From here on it is a normal JSONL file: replace pixel values by percentages or `{{ theme.* }}` where
   that helps, and deploy it with `openhasp-config-manager deploy`.
2. Turn the page's declarations into external ones, using the ids from the dump's comments:
   - tree: `Page()` becomes `Page(external=True)`, the containers go away (the leaves become a flat list) and every leaf gets its `obj_id`;
     `size=`/`weight=`/`at=` are removed (they raise in an external tree);
   - explicit calls: every `rect=...` becomes `obj_id=...`.

   Properties can stay (they are then set on bind and sync) or be deleted because the JSONL file has them now.
3. Restart haad.

With `Page(pin_ids=True)` (or explicit `obj_id`s on `add_*`) while the layout is still in code, the ids are fixed from the start, so step 2
does not have to look them up.

Nothing writes into `openhasp-configs/` automatically: that directory is hand-maintained (and its own git repository), and generated files
are kept apart from it, like `controllers/generated/` in haad projects.

## 7. Implementation plan

### Phase 0: pin today's behaviour, before any change

The `openhasp_config_manager/haad` package has no tests today (`tests/ad/` only instantiates the old AppDaemon controller), and haad-home's
plates depend on its exact behaviour. The API may change (§3, 4.4: `entity=`, `on_click`, `register_objects()`), so the tests pin
*behaviour* at the package's boundaries (traffic to the plate, calls into haad), not the shape of the API. Before the first change:

- [x] **Test environment**: these tests need haad, and with it Python 3.14. They run in haad's uv environment (which already has
      openhasp-config-manager as an editable dependency, and `pytest-cov`): `make test-haad`, see `tests/haad/README.md`. Without haad
      (the poetry environment), `tests/conftest.py` skips them. (QUESTIONS.md 1)
- [x] **A fake `OpenHaspClient` at the transport boundary**: a subclass with `_mqtt_client` and `_webservice_client` replaced by recorders,
      so `OpenHaspClient`'s own topic and payload formatting is part of what the tests pin. It also delivers `LWT`, `state/idle` and
      `state/p<N>b<M>` messages to subscribers.
- [x] **Characterization tests** for every public class and method in `controller.py`, `plate/`, `page/`, `objects/` and `util_openhasp.py`.
      They assert the exact traffic (topic and payload, in order) and the haad calls (`react_to`, service calls), on the haad `simulator`
      fixture (simulated time for `schedule()`, `react_to(immediately=True)`, state changes via `simulator.set_in_home_assistant(...)`).
- [x] **Golden-master scenarios**, one per page shape in haad-home (converters, `get_state` + trigger, switches with entity lists, scene
      buttons, images, plate behaviours), asserting the complete traffic of the scenario.
- [x] **100 % line and branch coverage** of `openhasp_config_manager/haad/`, enforced with `--cov-fail-under=100`.

The tests pin *current* behaviour, oddities included. Examples found while writing this design: `PlateController.setup_auto_brightness()`
checks `screen_controller._screen_brightness_task` but stores the new task on the plate, so the old listener is never cancelled;
`OpenHaspController.teardown_plate_setup()` reads `_plate_sync_timer_task`, which only exists after the first `schedule_sync()`. Fixing such
a thing is its own change that updates its test on purpose, never a side effect of this feature.

### Breaking changes

A breaking change is fine when it makes things simpler. Each one comes with, in the same change:

- the refactoring of all usages in `haad-home/controllers/openhasp/`;
- the migration of the phase-0 tests to the new API, with their traffic assertions unchanged. A traffic assertion only changes when the
  behaviour change is the point of the change, and then on its own.

Breaking changes in this design:

| Done | Change                                                        | Why                                                                  | Usages to refactor                    |
|------|---------------------------------------------------------------|----------------------------------------------------------------------|---------------------------------------|
| [x]  | `entity_id=` becomes `entity=` (`HAEntity`, id, or list)       | One argument name and type for leaves, `add_*` and `Bound`            | every `add_*` call with `entity_id=`  |
| [x]  | `on_click` becomes `async () -> None`                          | No usage reads `topic`/`payload`; actions can be passed directly      | about, printer                        |
| [x]  | `register_objects()` defaults to nothing                       | A page may use only `build_layout()`; the plate raises for pages without objects | none                       |

Additive changes: `build_layout()`, `obj_id` optional for owned objects (raises when neither `obj_id` nor `rect` is given), `add_label(text=)`
also accepts `str`, `add_button(on_click=)` optional, `trigger=`, `props=`/`Bound` (setters like `set_mode()` stay, for changes at
runtime), `PlateController.gui_defaults` instead of direct reads of
`deployment_controller.device.config.gui`, `DeploymentController` optional, the `LWT online` handler pushes owned pages.

### Phase 1 and later

In `haad`:

- [x] 1. `haad/util/composition.py` with `Composable`; `haad/ui/core.py` uses it (pure refactoring, see 4.10).

In `openhasp-config-manager/openhasp_config_manager/haad/`:

- [x] 2. `layout/geometry.py`: `Length`, `Rect`, `Padding` and the split functions. Pure functions, unit-tested without haad.
- [x] 3. `layout/theme.py`: `Theme`, `Icon`.
- [x] 4. `layout/components.py`: `LayoutNode` (extends `Composable`), `Page`, the containers (4.3) and leaves (4.4); the layout pass and
      `mount()` (one `add_*` call per leaf).
- [x] 5. `layout/render.py`: renders the owned objects of a page to JSONL dicts (theme, dimensions, validation; reusing the processors from
      `processing/` and `validation/`).
- [x] 6. `objects/__init__.py`: `ObjectController` gets `owned`, `jsonl`, `parent`; new generic `add_object`.
- [x] 7. `page/__init__.py`: `build_layout()` hook, `register_objects()` default, `entity=`, optional `obj_id`, `rect`/`props`/`parent`
      on all `add_*` methods, `trigger=`, `Bound` support, id allocation, `Page(external=True)` mounting.
- [x] 8. `plate/__init__.py`: `Screen`, `GuiDefaults`, new `PlateConfig` fields, `render_layout()`, `push_layout(clear: bool)` with 2 kB
      batching, `gui_defaults` accessor, page-0 `prev`/`next`.
- [x] 9. `plate/device_factory.py`: builds an in-memory `Device` from `controller_config()` + `PlateConfig`.
- [x] 10. `layout/dump.py`: writes the layout dumps (§6.1).
- [x] 11. `controller.py`: `DeploymentController` only with `config_dir`; clear-and-push on setup and on `LWT online` (QUESTIONS.md 33).

In `haad-home/controllers/openhasp/`:

- [x] 12. `theme.py` (from `openhasp-configs/theme.yaml`), `layout/navbar.py`, the page frame in `MarkusCodePageController`
        (not `MarkusPageController`: its flash pages would become mixed pages), `layout/parts.py` with `light_row()`.
- [ ] 13. Migrate one page (e.g. `markus.py`) on `wt32sc01plus_2`, then the rest. Not started: it changes a deployed plate and needs
        its JSONL removed from flash (QUESTIONS.md 30). Instead, the first code-defined page is a new one: `page/alerts.py`
        (`AlertsPage`, demo alerts) as page 4 of `wt32sc01plus_2`.

## 8. Testing

- Phase 0 (§7): characterization tests and 100 % coverage of the existing package, before anything changes. Later changes migrate and
  extend them; coverage stays at 100 %.
- Parity: the same page declared in all four combinations of §3 (the owned ones with equal layouts) produces the same bindings, and the two
  owned variants push the same JSONL.
- Geometry and rendering: plain unit tests on `Rect`, on the layout pass (`Row`/`Column`/`Grid` with sizes, weights, gaps, padding,
  rounding, `at=`) and on the rendered JSONL dicts of a page (no device, no MQTT).
- Tree building: nesting via `with`, a leaf outside a `Page` raises, `.obj` before mount raises, a `haad.ui` component inside an openHASP
  container (and the other way round) does not attach to it, `Page(external=True)` mounts bindings without pushing, requires `obj_id`
  and rejects containers and sizes,
  `Bound` registers a reaction and a `StateUpdater` entry, a `Bound` on a time trigger without `get_state` raises.
- Controller level: the haad `simulator` fixture with a fake `OpenHaspClient` that records `clear_page`/`jsonl`/`set_object_properties`
  calls and lets a test emit `LWT` and `state/p1bN` events. Like all haad fakes it must have the shape of the real client (same method names and
  signatures), ideally by subclassing it with the MQTT/HTTP layer replaced. `OpenHaspClient` keeps its own MQTT connection next to haad's
  `MQTTManager` (that is fine in production, see §5.2), so the simulator's MQTT does not see plate traffic: the fake client is the only way to
  observe it. Tests to have: the initial push clears owned pages before the first property update; `LWT online` clears and pushes again;
  payloads stay below 2 kB; mixing owned and external objects on a page raises; auto ids skip explicit ids; `pin_ids=True` without `obj_id`
  raises; the dump matches the pushed objects; a click event reaches `on_click` of an owned button.

## 9. Possible later additions

1. **Flash delivery for code-defined pages**: upload the rendered page as `L:/haad_p<N>.jsonl` via the HTTP API when its hash changed, and `run`
   it, while the code stays the source of truth. An automated alternative to freezing (§6.1), at the cost of flash writes and HTTP credentials.
2. **Asset upload**: an `assets=` field on `PlateConfig` that uploads fonts and images by hash via `OpenHaspClient.upload_file()`. This would
   remove the last reason to keep a `config_dir` for a code-defined plate.
