from pathlib import Path
from unittest import TestCase


class TestBase(TestCase):
    cfg_root = Path("./test_cfg_root")
    output = Path("./test_output")
