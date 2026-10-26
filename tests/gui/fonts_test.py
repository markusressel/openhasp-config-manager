from openhasp_config_manager.gui.domain.fonts import font_size


def test_font_size_of_built_in_fonts_and_font_files():
    assert font_size(24) == 24
    assert font_size("fonts_roboto24") == 24
    assert font_size("arial_20") == 20
    assert font_size("no_size") == 25
    assert font_size(None, default=17) == 17
