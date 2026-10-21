"""
The component tree of code-defined page layouts (README §4.2-4.4): a `Page` with containers and leaves, nested with `with`
blocks like the haad dashboards (`haad.ui`).

Containers only compute positions (except `Panel`, which is an openHASP object). Leaves are openHASP objects: mounting a
page calls the matching `PageController.add_*` method once per leaf, so a leaf has exactly the bindings of an add_* call.
"""
import math
import os
import sys
from typing import Any, Awaitable, Callable, Dict, Generic, List, Literal, Optional, Sequence, TypeVar, TYPE_CHECKING

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

        page = self.page
        if page is not None and page is not self and page.external:
            if isinstance(self, (Container, Spacer)):
                raise ValueError(f"{type(self).__name__} in Page(external=True): the layout is on the plate's flash")
            if size is not None or weight is not None or at is not None:
                raise ValueError(f"{type(self).__name__}: size=, weight= and at= in Page(external=True): the layout is on the plate's flash")

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
            else:
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
            return [Rect(content.x + offset, content.y, length, content.h) for offset, length in split(content.w, sizes, self.gap)]
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
        return cells[:len(children)]


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

    def layout(self, width: int, height: int):
        """The layout pass: computes the rectangles of all nodes, for a screen of the given size."""
        self._place(Rect(0, 0, width, height))

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
                raise ValueError(f"{reason} needs an obj_id on every leaf, missing on: "
                                 + ", ".join(f"{type(leaf).__name__} ({leaf.declaration})" for leaf in missing))
        page.reserve_ids([node.obj_id for node in self.nodes() if isinstance(node, (Leaf, Panel)) and node.obj_id is not None])
        if not self.external and self.rect is None:
            raise ValueError("Page.mount() of an owned page needs a layout() first")
        await self._mount_children(self, page, parent=None)

    async def _mount_children(self, node: LayoutNode, page: "PageController", parent: Optional[ObjectController]):
        for child in node.children:
            if isinstance(child, Leaf):
                await child._mount(page, None if self.external else child.rect, parent)
            elif isinstance(child, Panel):
                await child._mount(page, child.rect, parent)
                await self._mount_children(child, page, child.obj)
            else:
                await self._mount_children(child, page, parent)


class Spacer(LayoutNode):
    """Takes space in a `Row`/`Column`, and nothing else."""


class _Mounted(Generic[T]):
    """A node that becomes an openHASP object when its page is mounted."""

    obj_id: Optional[int]
    declaration: Optional[str]
    _obj: Optional[T] = None

    @property
    def obj(self) -> T:
        """The object controller this node was mounted as (available from register_objects() on)."""
        if self._obj is None:
            raise RuntimeError(f"{type(self).__name__} ({self.declaration}) is not mounted yet: use .obj from register_objects() on")
        return self._obj

    def _mounted(self, obj: T) -> T:
        obj.declaration = f"{self.declaration} {type(self).__name__}"
        self._obj = obj
        return obj


class Panel(_Linear, _Mounted[GenericObjectController]):
    """
    Places its children like a `Row` (`direction="row"`) or a `Column`, but it *is* an openHASP object (`obj`, with
    background, border, radius, ...): its children are created with `parentid` and positions relative to it.
    """

    def __init__(self, gap: int = 0, padding: int | Padding = 0, direction: Literal["row", "column"] = "column",
                 obj_id: Optional[int] = None, size: Optional[Length] = None, weight: Optional[float] = None,
                 at: Optional[Rect] = None, **props):
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

    def __init__(self, obj_id: Optional[int] = None, size: Optional[Length] = None, weight: Optional[float] = None,
                 at: Optional[Rect] = None, **props):
        super().__init__(size=size, weight=weight, at=at)
        self.obj_id = obj_id
        self.props: Dict[str, Any] = props

    async def _mount(self, page: "PageController", rect: Optional[Rect], parent: Optional[ObjectController]):
        self._mounted(await self._add(page, dict(obj_id=self.obj_id, rect=rect, props=self.props, parent=parent)))

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> T:
        raise NotImplementedError()


class Label(Leaf[LabelObjectController]):
    """A `label`, see PageController.add_label()."""

    def __init__(self, text: str | Callable[[Any], str] = lambda x: str(x), entity: "EntityRef | Sequence[EntityRef]" = None,
                 attribute: Optional[str] = None, get_state: Optional[Callable[[], Awaitable[Any]]] = None,
                 trigger: Optional[TriggerInput] = None, **kwargs):
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

    def __init__(self, entity: "EntityRef | Sequence[EntityRef]" = None, get_state: Optional[Callable[[], Awaitable[Any]]] = None,
                 trigger: Optional[TriggerInput] = None, **kwargs):
        super().__init__(**kwargs)
        self.binding = dict(entity=entity, get_state=get_state, trigger=trigger)

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> SwitchObjectController:
        return await page.add_switch(**self.binding, **common)


class Slider(Leaf[SliderObjectController]):
    """A `slider`, see PageController.add_slider()."""

    def __init__(self, entity: "EntityRef | Sequence[EntityRef]" = None, get_state: Optional[Callable[[], Awaitable[Any]]] = None,
                 on_changed: Optional[Callable[[Any], Awaitable[None]]] = None,
                 on_released: Optional[Callable[[Any], Awaitable[None]]] = None,
                 trigger: Optional[TriggerInput] = None, **kwargs):
        super().__init__(**kwargs)
        self.binding = dict(entity=entity, get_state=get_state, on_changed=on_changed, on_released=on_released, trigger=trigger)

    async def _add(self, page: "PageController", common: Dict[str, Any]) -> SliderObjectController:
        return await page.add_slider(**self.binding, **common)


class Bar(Leaf[BarObjectController]):
    """A `bar`, see PageController.add_bar()."""

    def __init__(self, entity: "EntityRef | Sequence[EntityRef]" = None, get_state: Optional[Callable[[], Awaitable[Any]]] = None,
                 transform_value: Optional[Callable[[Any], int]] = None, trigger: Optional[TriggerInput] = None, **kwargs):
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


def _declaration_site() -> str:
    """`file.py:line` of the first caller outside this package."""
    frame = sys._getframe(1)
    while "openhasp_config_manager/haad/" in frame.f_code.co_filename:
        frame = frame.f_back
    return f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno}"
