from openhasp_config_manager.processing.references import (
    find_font_references,
    find_image_references,
    font_file_name,
    matching_names,
)


def test_image_references_of_one_line_are_found_separately():
    text = '{"src": "L:/a.png", "text": "L:/b.png", "x": 1}'

    assert find_image_references(text) == {"a.png", "b.png"}


def test_image_references_in_commands_and_binary_images():
    assert find_image_references("p1b2.src=L:/folder_icon.bin") == {"folder_icon.bin"}


def test_image_references_ignore_other_files_and_comments():
    text = '// "src": "L:/commented.png"\nrun L:/page.jsonl\n{"src": "L:/used.png"}'

    assert find_image_references(text) == {"used.png"}


def test_image_reference_needs_the_whole_extension():
    assert find_image_references('"src": "L:/a.png.bak"') == set()


def test_font_references_in_json_and_commands():
    text = '{"text_font": "arial20", "value_font10": "mono_16", "text_color": "red"}\np1b2.text_font=other30\np1b3.text_font = "x12"'

    assert find_font_references(text) == {"arial20", "mono_16", "other30", "x12"}


def test_built_in_fonts_are_numbers():
    assert find_font_references('{"text_font": "24", "value_font": 32}\np1b2.text_font=16') == set()


def test_font_references_ignore_comments():
    assert find_font_references('// "text_font": "arial20"') == set()


def test_font_file_of_a_binary_font():
    assert font_file_name("arial_20", ["arial_20.bin", "x.png"]) == "arial_20.bin"


def test_font_file_of_a_truetype_font_has_the_size_at_the_end():
    assert font_file_name("arial20", ["arial.ttf"]) == "arial.ttf"
    assert font_file_name("roboto220", ["roboto2.ttf", "roboto.ttf"]) == "roboto2.ttf"
    assert font_file_name("arial", ["arial.ttf"]) is None


def test_binary_font_wins_over_truetype_font():
    assert font_file_name("arial20", ["arial.ttf", "arial20.bin"]) == "arial20.bin"


def test_font_file_missing():
    assert font_file_name("arial20", ["other.ttf"]) is None


def test_matching_names_match_the_whole_name():
    names = ["a_icon.png", "a_icon.png.bak", "b.bin"]

    assert matching_names(["a_*.png", "b.?in"], names) == ["a_icon.png", "b.bin"]
    assert matching_names([], names) == []
