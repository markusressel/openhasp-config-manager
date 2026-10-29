"""
The component tree of code-defined page layouts (README §4.2-4.4): a `Page` with containers and leaves, nested with `with`
blocks like the haad dashboards (`haad.ui`).

Containers only compute positions (except `Panel`, which is an openHASP object). Leaves are openHASP objects: mounting a
page calls the matching `PageController.add_*` method once per leaf, so a leaf has exactly the bindings of an add_* call.
"""

import asyncio
import math
import os
import sys
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Hashable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
    TYPE_CHECKING,
)

from haad.triggers.resolver import TriggerInput
from haad.util.composition import Composable
from openhasp_config_manager.haad.layout.geometry import Length, Padding, Rect, Size, Weight, split
from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.haad.objects.button import ButtonObjectController, SceneButtonObjectController
from openhasp_config_manager.haad.objects.generic import GenericObjectController
from openhasp_config_manager.haad.objects.image import ImageObjectController
from openhasp_config_manager.haad.objects.label import LabelObjectController
from openhasp_config_manager.haad.objects.progress import BarObjectController
from openhasp_config_manager.haad.objects.slider import SliderObjectController
from openhasp_config_manager.haad.objects.switch import SwitchObjectController

if TYPE_CHECKING:
    from openhasp_config_manager.haad.page import EntityRef, PageController
    from openhasp_config_manager.model import PartObject

T = TypeVar("T", bound=ObjectController)


class LayoutNode(Composable, family=True):
    """
    A node of a page layout. Inside a `Row`/`Column`, every node takes `size=` (pixels or a percentage of the parent) or
    `weight=` (a share of the rest, default 1) along the main axis, and fills the cross axis. `at=Rect(...)` places it at a
    fixed rectangle relative to its parent instead, outside the flow.
    """

    def __init__(self, *, size: Optional[Length] = None, weight: Optional[float] = None, at: Optional[Rect] = None):
        super().__init__()
        if self.parent is None and not isinstance(self, Page):
            raise ValueError(f"{type(self).__name__} created outside of a `with Page()` block: it would never reach the plate")
        if size is not None and weight is not None:
            raise ValueError(f"{type(self).__name__}: size= and weight= exclude each other")
        self.size = size
        self.weight = weight
        self.at = at
        # where the node was declared, for the layout dumps
        self.declaration = _declaration_site()
        # set by the layout pass: the node's rectangle, relative to the openHASP object it is placed in (or the screen)
        self.rect: Optional[Rect] = None
        # whether the node is hidden by a `hidden=Bound(...)`: it takes no space in its parent's flow then
        self.collapsed = False

        page = self.page
        if page is not None and page is not self and page.external:
            if isinstance(self, (Container, Spacer)):
                raise ValueError(f"{type(self).__name__} in Page(external=True): the layout is on the plate's flash")
            if size is not None or weight is not None or at is not None:
                raise ValueError(
                    f"{type(self).__name__}: size=, weight= and at= in Page(external=True): the layout is on the plate's flash"
                )

    @property
    def page(self) -> Optional["Page"]:
        node = self
        while node.parent is not None:
            node = node.parent
        return node if isinstance(node, Page) else None

    @property
    def main_axis_size(self) -> Size:
        if self.size is not None:
            return self.size
        return Weight(self.weight if self.weight is not None else 1)

    def leaves(self) -> List["Leaf"]:
        """The leaves of this subtree, in declaration order."""
        result = []
        for child in self.children:
            if isinstance(child, Leaf):
                result.append(child)
            result.extend(child.leaves())
        return result

    def nodes(self) -> List["LayoutNode"]:
        """All nodes of this subtree below this node, in declaration order."""
        result = []
        for child in self.children:
            result.append(child)
            result.extend(child.nodes())
        return result

    def _place(self, rect: Rect):
        """Layout pass: places this node at `rect` and its children inside it."""
        self.rect = rect

    async def set_collapsed(self, collapsed: bool):
        """
        Hides or shows the node in the flow of its parent: the layout is computed again without a collapsed node, and the
        objects that moved or changed their size are updated on the plate. Called when a bound `hidden` changes.
        """
        if collapsed == self.collapsed:
            return
        self.collapsed = collapsed
        page = self.page
        # nothing to move before the first layout pass
        if page.rect is not None:
            await page.relayout()


class Container(LayoutNode):
    """A node that places its children; it is no object on the plate (except `Panel`)."""

    def __init__(self, padding: int | Padding = 0, **sizing):
        super().__init__(**sizing)
        self.padding = Padding.of(padding)

    def _content(self, rect: Rect) -> Rect:
        """The area the children are placed in, in the same coordinates as `rect`."""
        return rect.inset(self.padding)

    def _place(self, rect: Rect):
        super()._place(rect)
        content = self._content(rect)
        flow = []
        for child in self.children:
            if child.at is not None:
                child._place(child.at.resolve(content.w, content.h).offset(content.x, content.y))
            elif not child.collapsed:
                flow.append(child)
        for child, child_rect in zip(flow, self._arrange(content, flow)):
            child._place(child_rect)

    def _arrange(self, content: Rect, children: Sequence[LayoutNode]) -> List[Rect]:
        raise NotImplementedError()


class _Linear(Container):
    _horizontal: bool

    def __init__(self, gap: int = 0, padding: int | Padding = 0, **sizing):
        super().__init__(padding=padding, **sizing)
        self.gap = gap

    def _arrange(self, content: Rect, children: Sequence[LayoutNode]) -> List[Rect]:
        sizes = [child.main_axis_size for child in children]
        if self._horizontal:
            return [
                Rect(content.x + offset, content.y, length, content.h) for offset, length in split(content.w, sizes, self.gap)
            ]
        return [Rect(content.x, content.y + offset, content.w, length) for offset, length in split(content.h, sizes, self.gap)]


class Column(_Linear):
    """Places its children top to bottom."""

    _horizontal = False


class Row(_Linear):
    """Places its children left to right."""

    _horizontal = True


class Grid(Container):
    """Places its children in equal cells, row by row. The number of rows follows from the number of children."""

    def __init__(self, columns: int, gap: int = 0, padding: int | Padding = 0, **sizing):
        super().__init__(padding=padding, **sizing)
        if columns < 1:
            raise ValueError(f"A grid needs at least one column: {columns}")
        self.columns = columns
        self.gap = gap

    def _arrange(self, content: Rect, children: Sequence[LayoutNode]) -> List[Rect]:
        for child in children:
            if child.size is not None or child.weight is not None:
                raise ValueError(f"{type(child).__name__} in a Grid: grid cells are equal, size= and weight= don't apply")
        if not children:
            return []
        rows = math.ceil(len(children) / self.columns)
        cells = [cell for row in content.grid(rows, self.columns, self.gap) for cell in row]
        return cells[: len(children)]


class Stack(Container):
    """Places all its children in the same area, on top of each other (e.g. a label on a bar)."""

    def _arrange(self, content: Rect, children: Sequence[LayoutNode]) -> List[Rect]:
        return [content] * len(children)


class Page(Column):
    """
    The root of a page's layout, returned by `PageController.build_layout()`. Its children are placed top to bottom, in
    the full screen minus `padding` (e.g. the height of a page-0 navbar).

    - `external=True`: the layout is on the plate's flash (JSONL). The page is then a flat list of leaves, each with its
      `obj_id`; containers, `size=`, `weight=` and `at=` raise.
    - `pin_ids=True`: every leaf needs an explicit `obj_id`, so the page can later be frozen into a JSONL file (§6.1).
    """

    def __init__(self, padding: int | Padding = 0, external: bool = False, pin_ids: bool = False):
        if Page.active_parent() is not None:
            raise ValueError("A Page can't be nested in another layout node")
        super().__init__(padding=padding)
        self.external = external
        self.pin_ids = pin_ids
        # held while the tree and the objects of the page change at runtime (collapsing, `Repeat`)
        self.lock = asyncio.Lock()
        self.controller: Optional["PageController"] = None

    def layout(self, width: int, height: int):
        """The layout pass: computes the rectangles of all nodes, for a screen of the given size."""
        self._place(Rect(0, 0, width, height))

    async def relayout(self):
        """
        The layout pass again, after a node collapsed or reappeared (`set_collapsed()`): sends the new position and size
        of every mounted object that changed to the plate, and keeps its rendered JSONL up to date, so a push after a
        reconnect has the current layout.
        """
        async with self.lock:
            await self.apply_layout()

    async def apply_layout(self):
        """relayout() for a caller that holds `lock`."""
        self.layout(self.rect.w, self.rect.h)
        for node in self.nodes():
            if isinstance(node, Part) and node.rect != node._area:
                raise ValueError(
                    f"Part({node.path}) ({node.declaration}) moved from {node._area} to {node.rect}: a part is rendered for "
                    f"the rectangle it has when the page is mounted, it can't move"
                )
            obj = node._obj if isinstance(node, _Mounted) else None
            # collapsed nodes keep their old rect
            if obj is None or obj.rect is None or node.rect == obj.rect:
                continue
            changed = {
                key: getattr(node.rect, key)
                for key in ("x", "y", "w", "h")
                if getattr(node.rect, key) != getattr(obj.rect, key)
            }
            obj.rect = node.rect
            obj.jsonl.update(changed)
            await obj.send_properties(changed)

    async def expand(self):
        """Builds the items of the page's `Repeat`s, before the first layout pass."""
        await self.expand_nodes(self.children)

    async def expand_nodes(self, nodes: Sequence["LayoutNode"]):
        for node in nodes:
            if isinstance(node, Repeat):
                await node.reconcile()
            await self.expand_nodes(node.children)

    async def activate(self):
        """Starts the `Repeat`s of the page: from now on they follow their sources, see `Repeat`."""
        await self.activate_nodes(self.children)

    async def activate_nodes(self, nodes: Sequence["LayoutNode"]):
        for node in nodes:
            if isinstance(node, Repeat):
                await node.activate()
            await self.activate_nodes(node.children)

    async def mount(self, page: "PageController"):
        """
        Creates the page's objects: one add_* call per leaf (and one object per Panel), in declaration order. Owned pages
        need a layout() first.
        """
        leaves = self.leaves()
        if self.external or self.pin_ids:
            missing = [leaf for leaf in leaves if leaf.obj_id is None]
            if missing:
                reason = "Page(external=True)" if self.external else "Page(pin_ids=True)"
                raise ValueError(
                    f"{reason} needs an obj_id on every leaf, missing on: "
                    + ", ".join(f"{type(leaf).__name__} ({leaf.declaration})" for leaf in missing)
                )
        self.controller = page
        page.layout_root = self
        page.reserve_ids([node.obj_id for node in self.nodes() if isinstance(node, (Leaf, Panel)) and node.obj_id is not None])
        if not self.external and self.rect is None:
            raise ValueError("Page.mount() of an owned page needs a layout() first")
        # the ids of the parts come from the config: they are known before the ids of the other objects are allocated
        parts = [node for node in self.nodes() if isinstance(node, Part)]
        for part in parts:
            part.expand(page)
        page.reserve_ids([obj_id for part in parts for obj_id in part.ids])
        await self.mount_nodes(self.children, parent=None)

    async def mount_nodes(self, nodes: Sequence[LayoutNode], parent: Optional[ObjectController]):
        """Creates the objects of `nodes` and their subtrees, below the object `parent`."""
        for child in nodes:
            if isinstance(child, Leaf):
                await child._mount(self.controller, None if self.external else child.rect, parent)
            elif isinstance(child, Panel):
                await child._mount(self.controller, child.rect, parent)
                await self.mount_nodes(child.children, child.obj)
            elif isinstance(child, Part):
                await child._mount(self.controller)
            else:
                await self.mount_nodes(child.children, parent)

    async def unmount_nodes(self, nodes: Sequence[LayoutNode]):
        """Removes the objects of `nodes` and their subtrees from the page and the plate, and stops their `Repeat`s."""
        subtree = [n for node in nodes for n in [node, *node.nodes()]]
        objects = [n._obj for n in subtree if isinstance(n, _Mounted) and n._obj is not None]
        for obj in objects:
            # the plate deletes the children of an object with it
            await self.controller.remove_object(obj, delete=not any(obj.parent is o for o in objects))
        for node in subtree:
            if isinstance(node, _Mounted):
                node._obj = None


class Spacer(LayoutNode):
    """Takes space in a `Row`/`Column`, and nothing else."""


class Repeat(_Linear):
    """
    A list that follows a source, like a `LazyColumn` in Jetpack Compose: places the nodes that `item` declares for every
    value of `source()`, like a `Column` (`direction="column"`) or a `Row`. When `trigger` fires, `source()` is evaluated again
    and the list is reconciled by `key`:

    - a value with a new key gets its nodes (`item(value)` runs once for it, inside this node), whose objects are created on
      the plate,
    - a key that is gone loses its objects (they are deleted on the plate, their reactions cancelled),
    - the nodes of the other keys keep their objects and only move.

    The content of an item that changes while its key stays has to follow its own source (`Bound`, `get_state`, `entity`).
    Nodes of the items should have a fixed `size=`, or they share the list's space. Not for `Page(external=True)`.
    """

    def __init__(
        self,
        source: Callable[[], Awaitable[Sequence[Any]]],
        item: Callable[[Any], Awaitable[None]],
        trigger: TriggerInput,
        key: Callable[[Any], Hashable] = lambda value: value,
        direction: Literal["row", "column"] = "column",
        gap: int = 0,
        padding: int | Padding = 0,
        **sizing,
    ):
        super().__init__(gap=gap, padding=padding, **sizing)
        if direction not in ("row", "column"):
            raise ValueError(f"Invalid direction: {direction!r}, expected 'row' or 'column'")
        self._horizontal = direction == "row"
        self.source = source
        self.item = item
        self.trigger = trigger
        self.key = key
        # the nodes of every item, by key
        self._items: Dict[Hashable, List[LayoutNode]] = {}
        self._reaction = None
        # whether an update removed this list with its item
        self._removed = False

    async def reconcile(self) -> tuple[List[LayoutNode], List[LayoutNode]]:
        """
        Builds the tree to the source's current values, in their order.
        :return: the nodes that were removed and the nodes that were added
        """
        values = list(await self.source())
        keys = [self.key(value) for value in values]
        if len(set(keys)) != len(keys):
            raise ValueError(f"Repeat ({self.declaration}): the keys of its values are not unique: {keys}")
        removed = [node for key in list(self._items) if key not in keys for node in self._items.pop(key)]
        for node in removed:
            self.children.remove(node)
            # a running update of a nested list is waiting for the page's lock: it must not touch the removed nodes
            for lists in [node, *node.nodes()]:
                if isinstance(lists, Repeat):
                    lists._removed = True
        added = []
        for value, key in zip(values, keys):
            if key not in self._items:
                start = len(self.children)
                with self:
                    await self.item(value)
                self._items[key] = self.children[start:]
                added.extend(self._items[key])
        self.children[:] = [node for key in keys for node in self._items[key]]
        return removed, added

    async def activate(self):
        """Follows the source from now on."""
        self._reaction = await self.page.controller.controller.react_to(
            trigger=self.trigger, action=self.update, immediately=True
        )

    async def deactivate(self):
        await self.page.controller.controller.cancel_reaction(self._reaction)
        self._reaction = None

    async def update(self):
        """Reconciles the list with the source, on the plate."""
        page = self.page
        async with page.lock:
            if self._removed:
                return
            removed, added = await self.reconcile()
            await page.unmount_nodes(removed)
            await page.expand_nodes(added)
            await page.apply_layout()
            if added:
                await page.mount_nodes(added, self._parent_object())
                objects = [
                    n._obj for top in added for n in [top, *top.nodes()] if isinstance(n, _Mounted) and n._obj is not None
                ]
                await page.controller.push_objects(objects)
            elif removed:
                page.controller.plate.render_layout(page.controller)
        # outside of the lock: cancelling a nested list waits for its running update, which needs the lock, and the new
        # nested lists update right away
        for lists in [n for top in removed for n in [top, *top.nodes()] if isinstance(n, Repeat)]:
            await lists.deactivate()
        await page.activate_nodes(added)

    def _parent_object(self) -> Optional[ObjectController]:
        """The object this list's nodes are placed in: the one of the closest panel above it."""
        node = self.parent
        while node is not None:
            if isinstance(node, Panel):
                return node.obj
            node = node.parent
        return None


class _Mounted(Generic[T]):
    """A node that becomes an openHASP object when its page is mounted."""

    obj_id: Optional[int]
    declaration: Optional[str]
    _obj: Optional[T] = None

    @property
    def obj(self) -> T:
        """The object controller this node was mounted as (available from register_objects() on)."""
        if self._obj is None:
            raise RuntimeError(
                f"{type(self).__name__} ({self.declaration}) is not mounted yet: use .obj from register_objects() on"
            )
        return self._obj

    def _mounted(self, obj: T) -> T:
        obj.declaration = f"{self.declaration} {type(self).__name__}"
        obj.layout_node = self
        self._obj = obj
        return obj


class Panel(_Linear, _Mounted[GenericObjectController]):
    """
    Places its children like a `Row` (`direction="row"`) or a `Column`, but it *is* an openHASP object (`obj`, with
    background, border, radius, ...): its children are created with `parentid` and positions relative to it.
    """

    def __init__(
        self,
        gap: int = 0,
        padding: int | Padding = 0,
        direction: Literal["row", "column"] = "column",
        obj_id: Optional[int] = None,
        size: Optional[Length] = None,
        weight: Optional[float] = None,
        at: Optional[Rect] = None,
        **props,
    ):
        super().__init__(gap=gap, padding=padding, size=size, weight=weight, at=at)
        if direction not in ("row", "column"):
            raise ValueError(f"Invalid direction: {direction!r}, expected 'row' or 'column'")
        self._horizontal = direction == "row"
        self.obj_id = obj_id
        self.props = props

    def _content(self, rect: Rect) -> Rect:
        # the children's coordinates are relative to the panel object
        return Rect(0, 0, rect.w, rect.h).inset(self.padding)

    async def _mount(self, page: "PageController", rect: Rect, parent: Optional[ObjectController]):
        self._mounted(await page.add_object("obj", obj_id=self.obj_id, rect=rect, props=self.props, parent=parent))


class Leaf(LayoutNode, _Mounted[T]):
    """An openHASP object. Keyword arguments that are not part of the signature are openHASP properties (values or Bound)."""

    def __init__(
        self,
        obj_id: Optional[int] = None,
        size: Optional[Length] = None,
        weight: Optional[float] = None,
        at: Optional[Rect] = None,
        **props,
    ):
        super().__init__(size=size, weight=weight, at=at)
        self.obj_id = obj_id
        self.props: Dict[str, Any] = props

    async def _mount(self, page: "PageController", rect: Optional[Rect], parent: Optional[ObjectController]):
        self._mounted(await self._add(page, dict(obj_id=self.obj_id, rect=rect, props=self.props, parent=parent)))

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> T:
        raise NotImplementedError()


class Label(Leaf[LabelObjectController]):
    """A `label`, see PageController.add_label()."""

    def __init__(
        self,
        text: str | Callable[[Any], str] = lambda x: str(x),
        entity: "EntityRef | Sequence[EntityRef]" = None,
        attribute: Optional[str] = None,
        get_state: Optional[Callable[[], Awaitable[Any]]] = None,
        trigger: Optional[TriggerInput] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.binding = dict(text=text, entity=entity, attribute=attribute, get_state=get_state, trigger=trigger)

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> LabelObjectController:
        return await page.add_label(**self.binding, **common)


class Button(Leaf[ButtonObjectController]):
    """A `btn`, see PageController.add_button()."""

    def __init__(self, text: Optional[str] = None, on_click: Optional[Callable[[], Awaitable[Any]]] = None, **kwargs):
        super().__init__(**kwargs)
        self.binding = dict(text=text, on_click=on_click)

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> ButtonObjectController:
        return await page.add_button(**self.binding, **common)


class SceneButton(Leaf[SceneButtonObjectController]):
    """A `btn` that activates a scene, see PageController.add_scene_button()."""

    def __init__(self, scene: str, text: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.binding = dict(scene=scene, text=text)

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> SceneButtonObjectController:
        return await page.add_scene_button(**self.binding, **common)


class Switch(Leaf[SwitchObjectController]):
    """A `switch`, see PageController.add_switch()."""

    def __init__(
        self,
        entity: "EntityRef | Sequence[EntityRef]" = None,
        get_state: Optional[Callable[[], Awaitable[Any]]] = None,
        trigger: Optional[TriggerInput] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.binding = dict(entity=entity, get_state=get_state, trigger=trigger)

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> SwitchObjectController:
        return await page.add_switch(**self.binding, **common)


class Slider(Leaf[SliderObjectController]):
    """A `slider`, see PageController.add_slider()."""

    def __init__(
        self,
        entity: "EntityRef | Sequence[EntityRef]" = None,
        get_state: Optional[Callable[[], Awaitable[Any]]] = None,
        on_changed: Optional[Callable[[Any], Awaitable[None]]] = None,
        on_released: Optional[Callable[[Any], Awaitable[None]]] = None,
        trigger: Optional[TriggerInput] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.binding = dict(
            entity=entity, get_state=get_state, on_changed=on_changed, on_released=on_released, trigger=trigger
        )

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> SliderObjectController:
        return await page.add_slider(**self.binding, **common)


class Bar(Leaf[BarObjectController]):
    """A `bar`, see PageController.add_bar()."""

    def __init__(
        self,
        entity: "EntityRef | Sequence[EntityRef]" = None,
        get_state: Optional[Callable[[], Awaitable[Any]]] = None,
        transform_value: Optional[Callable[[Any], int]] = None,
        trigger: Optional[TriggerInput] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.binding = dict(entity=entity, get_state=get_state, transform_value=transform_value, trigger=trigger)

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> BarObjectController:
        return await page.add_bar(**self.binding, **common)


class Image(Leaf[ImageObjectController]):
    """An `img`, see PageController.add_image(). Images on flash (`src="L:/..."`) must be deployed already."""

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> ImageObjectController:
        return await page.add_image(**common)


class Obj(Leaf[GenericObjectController]):
    """Any openHASP object type (`Obj(type="arc", ...)`), see PageController.add_object()."""

    def __init__(self, type: str, **kwargs):
        super().__init__(**kwargs)
        self.type = type

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> GenericObjectController:
        return await page.add_object(self.type, **common)


# the variable of a part with the rectangle the layout gives it, see `Part`
AREA = "area"

# the add_* method of PageController that creates the object controller of an object type of a part; other types: add_object()
_PART_OBJECT_METHODS = {
    "label": "add_label",
    "btn": "add_button",
    "switch": "add_switch",
    "slider": "add_slider",
    "bar": "add_bar",
    "img": "add_image",
}


class Part(LayoutNode):
    """
    The objects of a part of the plate's config directory (a `.jsonl` file for `!include`s, see the README of
    openhasp-config-manager, "Including objects"), rendered like a deployment renders an `!include` of it with `vars`
    (`ConfigModel.render_part`): with the variables of the plate's device, and the theme of the config (`theme.obj.*`), not
    the plate's `Theme`. Needs a plate with a `config_dir`.

    - **Placement**: the part gets the page as `page_index` and its rectangle as `area` (`area.x`, `area.y`, `area.w`,
      `area.h`, relative to the screen) and places its objects itself: from `area`, or like the parts of JSONL pages from
      `common.*` and other objects. A part that ignores `area` takes no space with `at=Rect(0, 0, 0, 0)`.
    - **References**: its objects can refer to the objects of the page (`b4.x`: as they are rendered) and to each other. The
      other nodes can't refer to them.
    - **Ids**: the part computes them from its variables, as in the config. The page keeps them free when it allocates the
      ids of its other objects; an explicit `obj_id` that is one of them raises.
    - **Objects**: `obj(id)` is the object controller of one of its objects (the type of its `obj`: a
      `LabelObjectController` for a label), from register_objects() on. They have no bindings: bind them with their methods
      (e.g. `LabelObjectController.bind_text()`).

    A part is rendered for the rectangle it has when the page is mounted, so it can't move later (a node before it that
    collapses raises). It can't be in a `Repeat` (yet), a `Panel` (its objects are placed on the page) or a
    `Page(external=True)` (its objects are pushed).
    """

    def __init__(self, path: str, vars: Optional[Mapping[str, Any]] = None, **sizing):
        """
        :param path: the part, relative to the config directory (as in an `!include`)
        :param vars: the variables of the part, like the `vars` of an `!include` (templates in them are rendered)
        :param sizing: size=, weight= or at=, like every node
        """
        super().__init__(**sizing)
        node = self.parent
        while node is not None:
            if isinstance(node, Repeat):
                raise ValueError(f"Part({path}) in a Repeat: the items of a list can't have parts (yet)")
            if isinstance(node, Panel):
                raise ValueError(f"Part({path}) in a Panel: the objects of a part are placed on the page, not in an object")
            node = node.parent
        if self.page.external:
            raise ValueError(f"Part({path}) in Page(external=True): the objects of a part are pushed by haad")
        self.path = path
        self.vars: Dict[str, Any] = dict(vars or {})
        if AREA in self.vars:
            raise ValueError(f"Part({path}): '{AREA}' of a part is its rectangle in the layout, not in vars")
        # set when the page is mounted: what the config knows of the part's objects before they are rendered, the
        # rectangle they are rendered for, and their object controllers
        self.part_objects: Optional[List["PartObject"]] = None
        self._area: Optional[Rect] = None
        self._objects: Dict[int, ObjectController] = {}

    @property
    def ids(self) -> List[int]:
        """The ids of the part's objects, known from the page's mount() on."""
        if self.part_objects is None:
            raise RuntimeError(
                f"Part({self.path}) ({self.declaration}) is not expanded yet: its ids are known from mount() on"
            )
        return [o.id for o in self.part_objects]

    def obj(self, obj_id: int, cls: type[T] = ObjectController) -> T:
        """
        The object controller of an object of the part (available from register_objects() on).
        :param obj_id: the id of the object, as the part computes it
        :param cls: the type it must have, e.g. LabelObjectController for a label
        :raises RuntimeError: if the page is not mounted yet
        :raises ValueError: if the part has no object with that id
        :raises TypeError: if the object is no `cls`
        """
        if not self._objects:
            raise RuntimeError(
                f"Part({self.path}) ({self.declaration}) is not mounted yet: use .obj() from register_objects() on"
            )
        if obj_id not in self._objects:
            raise ValueError(f"Part({self.path}) has no object {obj_id}, only: {', '.join(map(str, self._objects))}")
        obj = self._objects[obj_id]
        if not isinstance(obj, cls):
            raise TypeError(f"Object {obj.object_id} of Part({self.path}) is a {type(obj).__name__}, not a {cls.__name__}")
        return obj

    def _instance_vars(self) -> Dict[str, Any]:
        area = self._area
        return {**self.vars, AREA: {"x": area.x, "y": area.y, "w": area.w, "h": area.h}}

    def expand(self, page: "PageController"):
        """Reads the ids and types of the part's objects from the config, for the rectangle the part has now (see mount())."""
        model = page.plate.config_model
        if model is None:
            raise ValueError(f"Part({self.path}) ({self.declaration}): parts need a plate with a config_dir")
        screen = model.device.screen
        if (page.plate.screen.width, page.plate.screen.height) != (screen.width, screen.height):
            raise ValueError(
                f"Part({self.path}) ({self.declaration}): the plate's screen {page.plate.screen} is not the one of its device "
                f"in the config ({screen.width}x{screen.height}), which the part is rendered for"
            )
        self._area = self.rect
        objects = model.expand_part(self.path, page=page.index, vars=self._instance_vars())
        for part_object in objects:
            where = f"Part({self.path}) ({self.declaration}): {model.describe(part_object.origin)}"
            if part_object.page != page.index:
                raise ValueError(f"{where}: the object is on page {part_object.page}, not on page {page.index} of the part")
            if part_object.obj is None:
                raise ValueError(f"{where}: an object of a part on a page pushed by haad needs an obj")
        self.part_objects = objects

    async def _mount(self, page: "PageController"):
        model = page.plate.config_model
        for part_object in self.part_objects:
            method = _PART_OBJECT_METHODS.get(part_object.obj)
            if method is not None:
                obj = await getattr(page, method)(obj_id=part_object.id)
            else:
                obj = await page.add_object(part_object.obj, obj_id=part_object.id)
            obj.part = self
            obj.declaration = f"{self.declaration} Part {model.describe(part_object.origin)}"
            self._objects[part_object.id] = obj

    def render(self, page: "PageController", objects: Mapping[int, Mapping[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """
        The JSONL objects of the part (see `ConfigModel.render_part`), by id.
        :param objects: the other objects of the page by id, as they are rendered, for the references of the part
        """
        rendered = page.plate.config_model.render_part(self.path, page=page.index, vars=self._instance_vars(), objects=objects)
        return {obj.jsonl["id"]: dict(obj.jsonl) for obj in rendered}


def _declaration_site() -> str:
    """`file.py:line` of the first caller outside this package."""
    frame = sys._getframe(1)
    while "openhasp_config_manager/haad/" in frame.f_code.co_filename:
        frame = frame.f_back
    return f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno}"
