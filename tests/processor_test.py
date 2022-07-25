from openhasp_config_manager import ConfigProcessor
from tests import TestBase


class ProcessorTest(TestBase):

    def test_processor(self):
        processor = ConfigProcessor(self.cfg_root, self.output)

        devices = processor.analyze()
        processor.process(devices)
