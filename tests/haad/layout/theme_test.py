from openhasp_config_manager.haad.layout.theme import Theme


def test_theme_defaults():
    theme = Theme(obj={"btn": {"radius": 20}})

    assert theme.defaults_for("btn") == {"radius": 20}
    assert theme.defaults_for("label") == {}
    assert Theme().background_color == "#000000"
    assert Theme().defaults_for("btn") == {}
