from datetime import timedelta
from pathlib import Path
from typing import Awaitable, Callable, List

import pytest
import pytest_asyncio

from openhasp_config_manager.haad.controller import OpenHaspController
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.plate import deployment, device_factory
from tests.haad.fakes import FakeOpenHaspClient, FakePlate

CFG_ROOT = Path(__file__).parent.parent / "_test_cfg_root"
DEVICE_NAME = "test_device"

type PageFactory = Callable[[OpenHaspController], PageController]


class PlateUnderTest(OpenHaspController):
    """A plate controller whose `setup_plate()` adds the pages a test gives it."""

    page_factories: List[PageFactory] = []

    async def setup_plate(self):
        for factory in self.page_factories:
            self.add_page(factory(self))


@pytest.fixture
def plate(monkeypatch) -> FakePlate:
    """The fake plate every `OpenHaspClient` created by the haad package talks to."""
    fake = FakePlate()
    monkeypatch.setattr(deployment, "OpenHaspClient", lambda device: FakeOpenHaspClient(device, fake))
    monkeypatch.setattr(device_factory, "create_client", lambda device: FakeOpenHaspClient(device, fake))
    return fake


@pytest.fixture
def load_plate(simulator, plate, tmp_path) -> Callable[..., OpenHaspController]:
    """Creates a plate controller like haad-home does, with `config_dir` pointing to the test config root."""

    def _load(cls: type[OpenHaspController] = PlateUnderTest, pages: List[PageFactory] = (), **params) -> OpenHaspController:
        cls = type(cls.__name__, (cls,), {"page_factories": list(pages)}) if pages else cls
        return simulator.load_app(
            cls,
            name=params.pop("name", DEVICE_NAME),
            config_dir=params.pop("config_dir", CFG_ROOT),
            output_dir=params.pop("output_dir", tmp_path / "output"),
            layout_dump_dir=params.pop("layout_dump_dir", None),
            **params,
        )

    return _load


@pytest_asyncio.fixture
async def start_plate(simulator, plate, load_plate) -> Callable[..., Awaitable[OpenHaspController]]:
    """Starts a plate controller and runs its plate setup and first sync, like after a haad start with the plate online."""
    started = []

    async def _start(*args, **kwargs) -> OpenHaspController:
        controller = load_plate(*args, **kwargs)
        await simulator.start(controller)
        await simulator.advance(timedelta(seconds=2))
        await plate.settle()
        started.append(controller)
        return controller

    yield _start
    for controller in started:
        await controller.terminate()
        await plate.settle()


PLACEHOLDER_ID = 254


class EmptyPage(PageController):
    """A page for tests that add objects themselves. It has one object without binding, which sends nothing: a plate rejects pages without objects."""

    async def register_objects(self):
        await self.add_label(obj_id=PLACEHOLDER_ID)


def page_at(index: int, cls: type[PageController] = EmptyPage) -> PageFactory:
    return lambda controller: cls(
        controller=controller,
        state_updater=controller.state_updater,
        plate=controller.plate_controller,
        index=index,
    )


@pytest_asyncio.fixture
async def page(start_plate, plate) -> PageController:
    """Page 1 of a started plate, without objects. The traffic of the plate setup is cleared."""
    controller = await start_plate(pages=[page_at(1)])
    plate.clear()
    return controller.plate_controller.pages[1]
