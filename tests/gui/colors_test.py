from openhasp_config_manager.gui.domain.colors import Argb, parse_color
from tests import TestBase


class TestColors(TestBase):
    def test_parse(self):
        assert parse_color("#0D0F14") == Argb(13, 15, 20, 255, upper=True, has_alpha=False)
        assert parse_color("#0d0f14") == Argb(13, 15, 20, 255, upper=False)
        assert parse_color("#f80") == Argb(255, 136, 0, 255, upper=False)
        assert parse_color("#80FF8800") == Argb(255, 136, 0, 128, upper=True, has_alpha=True)

    def test_not_colors(self):
        for text in ("0D0F14", "#12", "#12345", "#GGGGGG", "#1234567", "", "red"):
            assert parse_color(text) is None

    def test_hex_keeps_the_style(self):
        assert parse_color("#0D0F14").hex() == "#0D0F14"
        assert parse_color("#0d0f14").hex() == "#0d0f14"
        # a short color is written in full
        assert parse_color("#f80").hex() == "#ff8800"
        assert parse_color("#80FF8800").hex() == "#80FF8800"

    def test_alpha_is_written_when_it_is_not_opaque(self):
        color = Argb(1, 2, 3, 128)
        assert color.hex() == "#80010203"
        assert Argb(1, 2, 3, 255, has_alpha=True).hex() == "#FF010203"
        assert Argb(1, 2, 3).hex() == "#010203"
