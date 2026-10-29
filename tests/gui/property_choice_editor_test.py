"""The dropdown of the properties panel for a property that takes one of a few values."""

from openhasp_config_manager.validation.property_values import value_choices


def _editor(value, obj_type="label", key="mode"):
    from openhasp_config_manager.gui.qt.widgets.pagelayout.property_editor import OpenHASPWidgetPropertyEditor

    applied = []
    combo = OpenHASPWidgetPropertyEditor._create_choice_editor(value_choices(obj_type, key), value, applied.append)
    return combo, applied


def test_the_values_with_their_meaning_and_the_current_one(qapp):
    combo, applied = _editor("dots")

    assert [combo.itemText(i).split(" \N{EM DASH} ")[0] for i in range(combo.count())] == [
        "expand", "break", "dots", "scroll", "loop", "crop",
    ]  # fmt: skip
    assert combo.currentText().startswith("dots \N{EM DASH} keep the size")
    # nothing is written while the list is made
    assert applied == []


def test_choosing_a_value_writes_it_with_its_type(qapp):
    combo, applied = _editor(0, obj_type="obj", key="bg_grad_dir")

    combo.setCurrentIndex(2)

    assert applied == [2]


def test_a_value_written_another_way_is_found(qapp):
    assert _editor("Scroll")[0].currentData() == "scroll"
    assert _editor("1", obj_type="obj", key="bg_grad_dir10")[0].currentData() == 1
    assert _editor("on", obj_type="line", key="line_rounded")[0].currentData() is True


def test_a_value_the_plate_doesnt_take_stays_and_is_marked(qapp):
    combo, applied = _editor("dot")

    assert combo.count() == 7
    assert combo.currentText() == "dot \N{EM DASH} not a value the plate takes"
    combo.setCurrentIndex(3)
    assert applied == ["dots"]
