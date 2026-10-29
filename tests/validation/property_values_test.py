import pytest

from openhasp_config_manager.validation.property_values import value_problems


def _problems(key, value, obj="label", **extra):
    return value_problems({"page": 1, "id": 2, "obj": obj, key: value, **extra}, key)


@pytest.mark.parametrize(
    "obj, key, value",
    [
        # parts and states the object has
        ("label", "bg_color", "#FFFFFF"),
        ("label", "text_color04", "#FFFFFF"),
        ("switch", "bg_color25", "#FFFFFF"),
        ("bar", "bg_color10", "#FFFFFF"),
        ("dropdown", "bg_color80", "#FFFFFF"),
        # one digit is the older scheme, which means something else per object type
        ("slider", "bg_color1", "#FFFFFF"),
        # whole numbers in their range, also as text
        ("obj", "bg_opa", 255),
        ("obj", "bg_opa", "0"),
        ("obj", "radius", -4),
        ("obj", "bg_grad_dir", 2),
        ("obj", "border_side", 15),
        ("obj", "clip_corner", 1),
        ("obj", "border_post", True),
        ("obj", "border_post", "on"),
        ("arc", "type", 2),
        ("dropdown", "direction", 3),
        ("obj", "page", 12),
        # properties that aren't known here
        ("obj", "x", "whatever"),
        ("roller", "mode", True),
        # a template that can't be rendered is a problem of its own
        ("obj", "bg_opa", "{{ missing }}"),
    ],
)
def test_values_the_plate_takes(obj, key, value):
    assert _problems(key, value, obj=obj) == []


def test_a_part_the_object_doesnt_have_is_styled_as_its_main_part():
    assert _problems("bg_color10", "#FFFFFF", obj="label") == [
        "a label has no part 10 (its parts: 0), the plate styles its main part instead"
    ]


def test_a_state_that_doesnt_exist_is_the_default_state():
    assert _problems("bg_color16", "#FFFFFF", obj="slider") == [
        "there is no state 6 (0 to 5), the plate styles the default state instead"
    ]


def test_part_state_and_range_are_reported_together():
    assert _problems("bg_opa17", 300, obj="label") == [
        "a label has no part 10 (its parts: 0), the plate styles its main part instead",
        "there is no state 7 (0 to 5), the plate styles the default state instead",
        "300 is not from 0 to 255",
    ]


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, "True is not a whole number from 0 to 1, the plate reads it as 0"),
        ("yes", "'yes' is not a whole number from 0 to 1, the plate reads it as 0"),
        (0.5, "0.5 is not a whole number from 0 to 1, the plate reads it as 0"),
        (2, "2 is not from 0 to 1"),
    ],
)
def test_a_number_property_reads_other_values_as_a_number(value, expected):
    assert _problems("clip_corner", value, obj="obj") == [expected]


def test_a_true_or_false_property():
    assert _problems("line_rounded", "maybe", obj="line") == [
        "'maybe' is not true or false (or on, off, yes, no, 1, 0), the plate reads it as false"
    ]


@pytest.mark.parametrize(
    "obj, key, value, expected",
    [
        ("slider", "type", 3, "3 is not from 0 to 2"),
        ("spinner", "direction", 2, "2 is not from 0 to 1"),
        ("obj", "page", 19, "19 is not from 0 to 12"),
    ],
)
def test_object_properties_in_a_range(obj, key, value, expected):
    assert _problems(key, value, obj=obj) == [expected]


def test_a_val_outside_of_min_and_max_is_shown_at_the_limit():
    assert _problems("val", 150, obj="bar") == ["150 is not from min 0 to max 100, the plate shows 100"]
    assert _problems("val", 5, obj="slider", min=10, max=20) == ["5 is not from min 10 to max 20, the plate shows 10"]
    assert _problems("val", 50, obj="arc") == []
    # a label has no min and max
    assert _problems("val", 150, obj="label") == []


@pytest.mark.parametrize(
    "action",
    [
        # the old way: a page the button leads to when it is released
        "prev",
        "Next",
        "back",
        "p1",
        "p12",
        # the commands per event, as an object or its text
        {"up": "page 2"},
        {"down": "p1b2.val=1", "long": ["page 1", "backlight off"], "hold": None},
        {"release": {"page": 1, "id": 3, "text": "Hi"}},
        '{"up": "page 2"}',
        # ArduinoJson also reads single quotes
        "{'up': 'page 2'}",
        # removes the action
        "",
        None,
        # a template that can't be rendered is a problem of its own
        "{{ missing }}",
        {"{{ event }}": "page 2"},
    ],
)
def test_actions_the_plate_runs(action):
    assert _problems("action", action, obj="btn") == []


@pytest.mark.parametrize(
    "action, expected",
    [
        ("page 2", "'page 2' is not prev, next, back, p<page> or a JSON object of events, the plate ignores it"),
        ("P2", "'P2' is not prev, next, back, p<page> or a JSON object of events, the plate ignores it"),
        (["page 2"], "['page 2'] is not prev, next, back, p<page> or a JSON object of events, the plate ignores it"),
        ('["page 2"]', "'[\"page 2\"]' is not prev, next, back, p<page> or a JSON object of events, the plate ignores it"),
        (2, "2 is not prev, next, back, p<page> or a JSON object of events, the plate ignores it"),
        ("p0", "'p0' is no page (pages 1 to 12), the plate ignores the action"),
        ("p", "'p' is no page (pages 1 to 12), the plate ignores the action"),
        ("p20", "'p20' is no page (pages 1 to 12), the plate doesn't change the page"),
        # HASP_NUM_PAGES + 1 to 3
        ("p13", "'p13' is page prev on the plate, there is no page 13 (pages 1 to 12)"),
        ("p15", "'p15' is page next on the plate, there is no page 15 (pages 1 to 12)"),
        # the page is an uint8_t: 256 is 0
        ("p256", "'p256' is no page (pages 1 to 12), the plate ignores the action"),
    ],
)
def test_actions_the_plate_ignores(action, expected):
    assert _problems("action", action, obj="btn") == [expected]


def test_the_plate_runs_actions_only_on_its_events():
    assert _problems("action", {"Up": "page 2", "click": "page 3", "lost": "page 4"}, obj="btn") == [
        "'Up' is not one of: down, up, long, hold, release (did you mean 'up'?), the plate never runs it",
        "'click' is not one of: down, up, long, hold, release, the plate never runs it",
        "'lost' is not one of: down, up, long, hold, release, the plate never runs it",
    ]


def test_the_plate_runs_only_commands_lists_and_objects():
    assert _problems("action", '{"up": 2, "down": ["page 1", true]}', obj="btn") == [
        "up: 2 is not a command, a list of commands or an object, the plate ignores it",
        "down: ['page 1', True] is not a command, a list of commands or an object, the plate ignores it",
    ]
