import orjson
import pytest

from openhasp_config_manager.haad.layout.components import Column, Label, Page, Panel, Switch
from openhasp_config_manager.haad.layout.geometry import Rect
from openhasp_config_manager.haad.layout.render import MAX_PAYLOAD_BYTES, batch_lines, render_page
from openhasp_config_manager.haad.layout.theme import Theme
from openhasp_config_manager.haad.objects.bound import Bound
from openhasp_config_manager.haad.page import PageController
from tests.haad.conftest import EmptyPage

THEME = Theme(background_color="#111111", obj={"label": {"text_color": "#FFFFFF", "align": "left"}, "switch": {"radius": 20}})


@pytest.fixture
def owned_page(page: PageController) -> PageController:
    """Page 1 without the placeholder object of the `page` fixture, which is external."""
    page.objects.clear()
    return page


def _config(page: PageController):
    return page.plate.deployment_controller.device.config


async def test_render_owned_objects(owned_page: PageController):
    with Page() as layout:
        with Panel(direction="row", size="10%", bg_color="#558B2F"):
            Label(text="Title", align="center", text_font="32")
        with Column(padding=8):
            Switch(entity="light.desk", border_width=Bound("sensor.co2", lambda x: 1))
    # the test device's screen is rotated: 480x320
    screen = _config(owned_page).openhasp_config_manager.device.screen
    layout.layout(screen.width, screen.height)
    await layout.mount(owned_page)
    await owned_page.add_label(rect=Rect("50%", "50%", "10%", 20), text="Explicit", props={"mode": "scroll"})

    rendered = render_page(owned_page, THEME, _config(owned_page), 480, 320)

    assert rendered == [
        {"page": 1, "id": 0, "bg_color": "#111111", "bg_grad_dir": 0},
        {"page": 1, "id": 1, "obj": "obj", "x": 0, "y": 0, "w": 480, "h": 32, "bg_color": "#558B2F"},
        # theme < typed args (text) < props; text_font normalized to int like in JSONL files
        {
            "page": 1,
            "id": 2,
            "obj": "label",
            "parentid": 1,
            "x": 0,
            "y": 0,
            "w": 480,
            "h": 32,
            "text": "Title",
            "align": "center",
            "text_font": 32,
            "text_color": "#FFFFFF",
        },
        # Bound properties are not pushed
        {"page": 1, "id": 3, "obj": "switch", "x": 8, "y": 40, "w": 464, "h": 272, "radius": 20},
        {
            "page": 1,
            "id": 4,
            "obj": "label",
            "x": 240,
            "y": 160,
            "w": 48,
            "h": 20,
            "mode": "scroll",
            "text": "Explicit",
            "text_color": "#FFFFFF",
            "align": "left",
        },
    ]
    assert owned_page.objects[3].jsonl == rendered[3]


async def test_render_percentages_relative_to_the_parent(owned_page: PageController):
    panel = await owned_page.add_object("obj", rect=Rect(10, 10, 100, 50))
    await owned_page.add_label(rect=Rect("50%", "50%", "50%", "50%"), parent=panel)

    rendered = render_page(owned_page, Theme(), _config(owned_page), 480, 320)

    assert rendered[2] == {"page": 1, "id": 2, "obj": "label", "parentid": 1, "x": 50, "y": 25, "w": 50, "h": 25}


async def test_render_external_page_renders_nothing(page: PageController):
    assert render_page(page, THEME, _config(page), 480, 320) == []


async def test_render_mixed_page_raises(page: PageController):
    await page.add_label(rect=Rect(0, 0, 1, 1))

    with pytest.raises(ValueError, match="Page 1 mixes owned objects \\(with a rect\\) and external objects .*: p1b254\\)"):
        render_page(page, THEME, _config(page), 480, 320)


async def test_render_validates(owned_page: PageController):
    await owned_page.add_label(rect=Rect(0, 0, 1, 1), props={"align": "middle"})

    with pytest.raises(AssertionError, match="Invalid 'align' string value"):
        render_page(owned_page, THEME, _config(owned_page), 480, 320)


async def test_render_rejects_objects_larger_than_a_payload(owned_page: PageController):
    await owned_page.add_label(rect=Rect(0, 0, 1, 1), text="x" * MAX_PAYLOAD_BYTES)

    with pytest.raises(ValueError, match="p1b1 is \\d+ bytes as JSONL, more than fits into one payload"):
        render_page(owned_page, THEME, _config(owned_page), 480, 320)


def test_batch_lines():
    objects = [{"id": i, "text": "x" * 20} for i in range(5)]
    line = len(orjson.dumps(objects[0]))

    assert batch_lines([]) == []
    assert batch_lines(objects) == ["\n".join(orjson.dumps(o).decode() for o in objects)]
    # two lines and their newline fit exactly
    batches = batch_lines(objects, max_bytes=2 * line + 1)
    assert [b.count("\n") + 1 for b in batches] == [2, 2, 1]
    assert all(len(b.encode()) <= 2 * line + 1 for b in batches)


async def test_empty_page_placeholder_is_external(page: PageController):
    assert isinstance(page, EmptyPage)
    assert not page.owned


async def test_render_page_0_without_page_object(start_plate):
    """Page 0 lies over every page: its page object keeps its (transparent) background."""
    from tests.haad.conftest import page_at
    from tests.haad.owned_plate_test import ExplicitPage, OwnedPlate

    controller = await start_plate(OwnedPlate, pages=[page_at(0, ExplicitPage)])

    assert [o["id"] for o in controller.plate_controller.rendered[0]] == [1]
