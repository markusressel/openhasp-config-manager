from openhasp_config_manager.ad.controller import OpenHaspController
from tests import TestBase


class OpenHaspControllerTest(TestBase):

    async def test_instantiation(self):
        ad = {}
        config_model = {}
        controller = OpenHaspController(ad, config_model)
