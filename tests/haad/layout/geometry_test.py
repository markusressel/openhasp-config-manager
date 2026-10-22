import pytest

from openhasp_config_manager.haad.layout.geometry import Padding, Rect, Weight, resolve_length, split


@pytest.mark.parametrize(
    "length, total, expected",
    [
        (48, 100, 48),
        ("25%", 480, 120),
        ("33.3%", 320, 106),  # rounded down, like ObjectDimensionsProcessor
        ("0%", 320, 0),
    ],
)
def test_resolve_length(length, total, expected):
    assert resolve_length(length, total) == expected


@pytest.mark.parametrize("length", ["25", "abc%", "-5%", 1.5, None])
def test_resolve_invalid_length(length):
    with pytest.raises(ValueError, match="Invalid length"):
        resolve_length(length, 100)


def test_resolve_bool_length():
    with pytest.raises(TypeError):
        resolve_length(True, 100)


def test_split_by_weights():
    assert split(100, [Weight(), Weight(), Weight()]) == [(0, 33), (33, 33), (66, 34)]
    assert split(100, [Weight(1), Weight(3)]) == [(0, 25), (25, 75)]


def test_split_rounding_never_leaves_gaps():
    for length in range(0, 200):
        for count in range(1, 8):
            parts = split(length, [Weight()] * count, gap=2) if length >= 2 * (count - 1) else None
            if parts is None:
                continue
            assert parts[0][0] == 0
            for (offset, size), (next_offset, _) in zip(parts, parts[1:]):
                assert offset + size + 2 == next_offset
            assert parts[-1][0] + parts[-1][1] == length


def test_split_fixed_sizes_and_gaps():
    # 48 fixed, 25% of 200 = 50, three gaps of 4: 90 left for the weights 1:1
    assert split(200, [48, Weight(), "25%", Weight()], gap=4) == [(0, 48), (52, 45), (101, 50), (155, 45)]


def test_split_only_fixed_sizes_leaves_the_rest_empty():
    assert split(100, [10, 20]) == [(0, 10), (10, 20)]


def test_split_nothing():
    assert split(100, []) == []


def test_split_too_small_raises():
    with pytest.raises(ValueError, match="need 110 pixels, only 100 available"):
        split(100, [60, 40, Weight()], gap=5)


def test_weight_must_be_positive():
    with pytest.raises(ValueError):
        Weight(0)


def test_padding():
    assert Padding() == Padding(0)
    assert Padding(8) == Padding(top=8, right=8, bottom=8, left=8)
    assert Padding(4, x=6) == Padding(top=4, right=6, bottom=4, left=6)
    assert Padding(y=2, bottom=48) == Padding(top=2, right=0, bottom=48, left=0)
    assert Padding.of(None) == Padding()
    assert Padding.of(3) == Padding(3)
    assert Padding.of(Padding(x=1)) == Padding(x=1)


def test_rect_resolve():
    assert Rect("10%", "50%", "100%", 48).resolve(320, 480) == Rect(32, 240, 320, 48)
    assert Rect("10%", 0, 1, 1).is_resolved is False
    assert Rect(1, 2, 3, 4).is_resolved is True


def test_rect_helpers_need_pixels():
    with pytest.raises(ValueError, match="resolve\\(\\) it against its parent first"):
        Rect("10%", 0, 100, 100).rows(1, 1)


def test_rect_inset():
    rect = Rect(10, 20, 100, 50)

    assert rect.inset(5) == Rect(15, 25, 90, 40)
    assert rect.inset(x=10) == Rect(20, 20, 80, 50)
    assert rect.inset(y=5) == Rect(10, 25, 100, 40)
    assert rect.inset(Padding(left=1, top=2)) == Rect(11, 22, 99, 48)
    with pytest.raises(ValueError, match="does not fit"):
        rect.inset(30)


def test_rect_offset():
    assert Rect(1, 2, 3, 4).offset(10, 20) == Rect(11, 22, 3, 4)


def test_rect_rows_cols_grid():
    rect = Rect(10, 10, 100, 60)

    assert rect.rows(1, 2) == [Rect(10, 10, 100, 20), Rect(10, 30, 100, 40)]
    assert rect.cols(1, 1, gap=10) == [Rect(10, 10, 45, 60), Rect(65, 10, 45, 60)]
    assert rect.grid(2, 2, gap=10) == [
        [Rect(10, 10, 45, 25), Rect(65, 10, 45, 25)],
        [Rect(10, 45, 45, 25), Rect(65, 45, 45, 25)],
    ]
