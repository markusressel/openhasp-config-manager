from openhasp_config_manager import ConfigProcessor
from tests import TestBase


class ProcessorTest(TestBase):

    def test_processor(self):
        processor = ConfigProcessor(self.cfg_root, self.output)

        devices = processor.analyze()
        processor.process(devices)

        file_count = 0
        for file in self.output.rglob("*.jsonl"):
            file_count += 1
            content = file.read_text()
            assert len(content) > 0
            for line in content.splitlines():
                assert line.startswith("{")
                assert line.endswith("}")

        assert file_count > 0
