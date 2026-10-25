from openhasp_config_manager.gui.domain.problems import Severity, find_problems, geometry_value


def _find(objects):
    return find_problems(objects, 480, 320)


def _obj(obj_id, x=0, y=0, w=10, h=10, **extra):
    return {"page": 1, "id": obj_id, "x": x, "y": y, "w": w, "h": h, **extra}


def test_objects_on_the_screen_have_no_problems():
    assert _find([_obj(1), _obj(2, x=470, w=10, y=310)]) == []


def test_an_object_outside_of_the_screen_is_a_warning_with_the_sides():
    inside, sticks_out = _obj(1), _obj(2, x=-4, y=300, w=20, h=30)

    [problem] = _find([inside, sticks_out])

    assert problem.severity == Severity.WARNING
    assert problem.obj is sticks_out
    assert problem.message == "p1b2 is outside of the screen: left by 4 px, bottom by 10 px"


def test_a_used_twice_id_is_an_error_and_comes_first():
    problems = _find([_obj(1, x=500), _obj(2), _obj(2)])

    assert [problem.severity for problem in problems] == [Severity.ERROR, Severity.WARNING]
    assert problems[0].message == "p1b2: the id is used by 2 objects"


def test_an_object_without_a_size_is_checked_with_the_size_it_is_drawn_with():
    [problem] = find_problems([{"page": 1, "id": 1, "x": 450, "y": 0}], 480, 320)

    assert problem.message == "p1b1 is outside of the screen: right by 50 px"


def test_an_object_without_position_and_size_is_on_the_screen():
    assert find_problems([{"page": 1, "id": 1}], 480, 320) == []


def test_a_position_that_is_not_a_number_is_an_error_and_drawn_with_the_default():
    # e.g. `{{ p3b20.y + 5 }}` while p3b20 doesn't exist
    broken = {"page": 1, "id": 2, "x": "{{ p1b1.x + 5 }}", "y": 10, "w": 20, "h": 20}

    problems = find_problems([broken], 480, 320)

    assert [(p.severity, p.message) for p in problems] == [(Severity.ERROR, "p1b2: x is not a number: {{ p1b1.x + 5 }}")]
    assert geometry_value(broken, "x") == 0
    assert geometry_value(broken, "y") == 10
    assert geometry_value({"w": True}, "w") == 80


def test_the_json_view_sorts_objects_with_values_that_are_not_numbers(qapp, settings):
    from openhasp_config_manager.gui.qt.widgets.pagelayout.jsonl_preview import PageJsonlPreviewWidget

    # two objects with the same id, one of them with a position that can't be rendered
    objects = [
        {"page": 1, "id": 2, "y": "{{ p1b9.y }}", "x": 1},
        {"page": 1, "id": 2, "y": 5, "x": 1},
        {"page": "{{ nope }}", "id": 1},
    ]

    widget = PageJsonlPreviewWidget()
    widget.set_objects(objects)
    assert [obj["id"] for obj in widget._objects] == [1, 2, 2]


def test_an_exception_in_a_slot_is_reported_instead_of_aborting(monkeypatch):
    import sys

    from openhasp_config_manager.cli.gui import install_exception_hook

    reported = []

    class _Failed:
        def emit(self, description, error):
            reported.append((description, error))

    class _Window:
        status = type("Status", (), {"failed": _Failed()})()

    printed = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: printed.append(args))
    install_exception_hook(_Window())

    try:
        raise ValueError("boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    assert printed and reported == [("Unexpected error (see the console)", "ValueError: boom")]
