from openhasp_config_manager.processing import VariableManager
from tests import TestBase


class TestVariableManager(TestBase):

    def test_get_variables_for_pathanalyze_whole_config(self, tmp_path):
        # GIVEN
        # TODO: write

        variable_manager = VariableManager(self.cfg_root)
        # WHEN
        devices = variable_manager.get_vars()

        # THEN
        assert len(devices) == 1

        components = devices[0].components
        assert len(components) == 6
