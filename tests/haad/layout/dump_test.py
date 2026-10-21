import orjson

from openhasp_config_manager.haad.layout.components import Label, Page
from openhasp_config_manager.haad.layout.dump import dump_lines
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.processing.preprocessor.jsonl_preprocessor import JsonlPreProcessor
from tests.haad.conftest import page_at
from tests.haad.owned_plate_test import OwnedPlate


class DumpedPage(PageController):
    async def build_layout(self) -> Page:
        with Page() as page:
            Label(text="Desk")
        return page


def test_dump_lines():
    objects = [{"page": 1, "id": 0}, {"page": 1, "id": 1, "obj": "label"}]

    assert dump_lines(objects, {1: "page.py:3 Label"}) == (
        '{"page":1,"id":0}\n'
        "// page.py:3 Label\n"
        '{"page":1,"id":1,"obj":"label"}\n'
    )


async def test_rendered_pages_are_dumped(start_plate, tmp_path):
    controller = await start_plate(OwnedPlate, pages=[page_at(1, DumpedPage)], layout_dump_dir=tmp_path / "haad")

    content = (tmp_path / "haad" / "test_device" / "p1.jsonl").read_text()
    lines = content.splitlines()
    assert lines[1].startswith("// dump_test.py:") and lines[1].endswith(" Label")
    # openhasp-config-manager reads it like any JSONL file: comments are skipped
    preprocessor = JsonlPreProcessor()
    parsed = [orjson.loads(preprocessor.cleanup_object_for_json_parsing(o)) for o in preprocessor.split_jsonl_objects(content)]
    assert parsed == controller.plate_controller.rendered[1]
