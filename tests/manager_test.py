from openhasp_config_manager.manager import ConfigManager
from tests import TestBase


class ConfigManagerTest(TestBase):

    def test_process_whole_config(self):
        manager = ConfigManager(self.cfg_root, self.output)

        devices = manager.analyze()
        manager.process(devices)

        file_count = 0
        for file in self.output.rglob("*.jsonl"):
            file_count += 1
            content = file.read_text()
            self.assertGreater(len(content), 0)
            for line in content.splitlines():
                self.assertTrue(line.startswith("{"))
                self.assertTrue(line.endswith("}"))

        self.assertGreater(file_count, 0)
