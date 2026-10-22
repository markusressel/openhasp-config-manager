from openhasp_config_manager.gui.domain.problems import Severity, find_problems


def _find(objects):
    return find_problems(objects, {id(obj): (obj["x"], obj["y"], obj["w"], obj["h"]) for obj in objects}, 480, 320)


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


def test_objects_that_are_not_drawn_are_left_alone():
    assert find_problems([{"page": 1, "id": 1}], {}, 480, 320) == []
