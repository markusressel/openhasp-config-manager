from openhasp_config_manager.ad.controller import OpenHaspController
from tests import TestBase


class OpenHaspControllerTest(TestBase):
    async def test_instantiation(self):
        ad = {}
        config_model = {}
        _ = OpenHaspController(ad, config_model)
