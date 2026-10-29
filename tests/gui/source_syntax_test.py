from pathlib import Path

from openhasp_config_manager.gui.domain.source.syntax import (
    Language,
    TokenKind,
    JsonlState,
    find_templates,
    language_of,
    tokenize_jsonl,
    tokenize_line,
)
from tests import TestBase


def _kinds(line, language=Language.JSONL):
    return [(token.text(line), token.kind) for token in tokenize_line(line, language)]


class TestLanguage(TestBase):
    def test_language_of_a_file(self):
        assert language_of(Path("a/page.jsonl")) == Language.JSONL
        assert language_of(Path("boot.cmd")) == Language.CMD
        assert language_of(Path("vars.yaml")) == Language.YAML
        assert language_of(Path("vars.YML")) == Language.YAML
        assert language_of(Path("config.json")) == Language.JSON
        assert language_of(Path("notes.txt")) == Language.TEXT
        assert tokenize_line("anything", Language.TEXT) == []


class TestJson(TestBase):
    def test_highlighted_like_jsonl(self):
        assert _kinds('  "ssid": "x", "port": 1883,', Language.JSON) == _kinds('  "ssid": "x", "port": 1883,')


class TestJsonl(TestBase):
    def test_object_on_one_line(self):
        assert _kinds('{"page": 1, "obj": "btn", "x": -2.5, "on": true, "t": null}') == [
            ("{", TokenKind.SYMBOL),
            ('"page"', TokenKind.KEY),
            (":", TokenKind.SYMBOL),
            ("1", TokenKind.NUMBER),
            (",", TokenKind.SYMBOL),
            ('"obj"', TokenKind.KEY),
            (":", TokenKind.SYMBOL),
            ('"btn"', TokenKind.STRING),
            (",", TokenKind.SYMBOL),
            ('"x"', TokenKind.KEY),
            (":", TokenKind.SYMBOL),
            ("-2.5", TokenKind.NUMBER),
            (",", TokenKind.SYMBOL),
            ('"on"', TokenKind.KEY),
            (":", TokenKind.SYMBOL),
            ("true", TokenKind.CONSTANT),
            (",", TokenKind.SYMBOL),
            ('"t"', TokenKind.KEY),
            (":", TokenKind.SYMBOL),
            ("null", TokenKind.CONSTANT),
            ("}", TokenKind.SYMBOL),
        ]

    def test_comment_runs_to_the_end_of_the_line(self):
        assert _kinds('  "a": 1, // a "comment" {') == [
            ('"a"', TokenKind.KEY),
            (":", TokenKind.SYMBOL),
            ("1", TokenKind.NUMBER),
            (",", TokenKind.SYMBOL),
            ('// a "comment" {', TokenKind.COMMENT),
        ]

    def test_slashes_in_a_string_are_no_comment(self):
        assert _kinds('"url": "http://x"')[-1] == ('"http://x"', TokenKind.STRING)

    def test_colors_are_tokens(self):
        assert _kinds('"c": "#ff8800"')[-1] == ('"#ff8800"', TokenKind.COLOR)
        assert _kinds('"c": "#fff"')[-1] == ('"#fff"', TokenKind.COLOR)
        assert _kinds('"c": "#ff88"')[-1] == ('"#ff88"', TokenKind.STRING)
        assert _kinds('"c": "#80ff8800"')[-1] == ('"#80ff8800"', TokenKind.COLOR)

    def test_colors_in_yaml(self):
        assert _kinds('  background_color: "#0D0F14"', Language.YAML) == [
            ("background_color", TokenKind.KEY),
            ('"#0D0F14"', TokenKind.COLOR),
        ]
        assert _kinds("c: '#fff' # white", Language.YAML)[1:] == [
            ("'#fff'", TokenKind.COLOR),
            ("# white", TokenKind.COMMENT),
        ]
        # an unquoted one is a comment in YAML, a mismatched quote is no color
        assert _kinds("c: #fff", Language.YAML)[-1][1] == TokenKind.COMMENT
        assert _kinds("c: \"#fff'", Language.YAML)[-1][1] == TokenKind.STRING

    def test_templates_are_split_out_of_strings(self):
        assert _kinds('"text": "a {{ b }} c"')[2:] == [
            ('"a ', TokenKind.STRING),
            ("{{ b }}", TokenKind.TEMPLATE),
            (' c"', TokenKind.STRING),
        ]

    def test_a_template_is_split_out_of_a_key_too(self):
        assert ("{{ k }}", TokenKind.TEMPLATE) in _kinds('"{{ k }}": 1')
        assert _kinds('"{{ k }}": 1')[0] == ('"', TokenKind.KEY)

    def test_escaped_quote_does_not_end_the_string(self):
        assert _kinds(r'"a": "x\"y"')[-1] == (r'"x\"y"', TokenKind.STRING)

    def test_unfinished_string_reaches_the_end_of_the_line(self):
        assert _kinds('"a": "open')[-1] == ('"open', TokenKind.STRING)
        assert _kinds('"a": "open\\')[-1] == ('"open\\', TokenKind.STRING)

    def test_unknown_characters_are_skipped(self):
        assert _kinds("nope") == []


class TestTemplates(TestBase):
    # where templates are is tested in template_rendering/checks_test (`template_spans`)
    def test_templates_are_tokens_at_their_offset(self):
        assert [(t.start, t.end, t.kind) for t in find_templates("{{ a }} {% b %}", offset=5)] == [
            (5, 12, TokenKind.TEMPLATE),
            (13, 20, TokenKind.TEMPLATE),
        ]


class TestCmd(TestBase):
    def test_command_and_arguments(self):
        assert _kinds("  run L:/{{ name }}.jsonl", Language.CMD) == [
            ("run", TokenKind.COMMAND),
            (" L:/", TokenKind.ARGUMENT),
            ("{{ name }}", TokenKind.TEMPLATE),
            (".jsonl", TokenKind.ARGUMENT),
        ]
        assert _kinds("page 1", Language.CMD) == [("page", TokenKind.COMMAND), (" 1", TokenKind.ARGUMENT)]
        assert _kinds("", Language.CMD) == []
        assert _kinds("   ", Language.CMD) == []


class TestYaml(TestBase):
    def test_key_value_and_comment(self):
        assert _kinds("  width: 480 # px", Language.YAML) == [
            ("width", TokenKind.KEY),
            ("480", TokenKind.NUMBER),
            ("# px", TokenKind.COMMENT),
        ]

    def test_constants_strings_templates_and_lists(self):
        assert _kinds("on: true", Language.YAML) == [("on", TokenKind.KEY), ("true", TokenKind.CONSTANT)]
        assert _kinds("- name: a{{ b }}", Language.YAML) == [
            ("name", TokenKind.KEY),
            ("a", TokenKind.STRING),
            ("{{ b }}", TokenKind.TEMPLATE),
        ]
        assert _kinds("- plain", Language.YAML) == [("- plain", TokenKind.STRING)]

    def test_hash_in_quotes_is_no_comment(self):
        assert _kinds('color: "#fff"', Language.YAML) == [("color", TokenKind.KEY), ('"#fff"', TokenKind.COLOR)]
        assert _kinds("color: '#fff' # c", Language.YAML)[-1] == ("# c", TokenKind.COMMENT)
        assert _kinds("# all", Language.YAML) == [("# all", TokenKind.COMMENT)]
        assert _kinds("a#b", Language.YAML) == [("a#b", TokenKind.STRING)]


class TestDirectives(TestBase):
    def _directive_keys(self, lines):
        state, result = JsonlState(), []
        for line in lines:
            tokens, state = tokenize_jsonl(line, state)
            result += [token.text(line) for token in tokens if token.kind == TokenKind.DIRECTIVE]
        return result, state

    def test_the_keys_of_a_directive(self):
        # GIVEN: `vars` and `for` of an object are no directive keys, nor are the keys inside of `vars`
        lines = [
            '{"!include": "a.jsonl", "vars": {"for": 1, "id": 2}, "for": {"i": [1]}}',
            '{"page": 1, "vars": 1, "for": 2}',
            "{",
            '  "!include": "a.jsonl",',
            '  "vars": {',
            '    "vars": 1',
            "  },",
            '  "for": {"i": [1, 2]}',
            "}",
            '{"for": 1}',
        ]

        # WHEN
        keys, state = self._directive_keys(lines)

        # THEN
        assert keys == ['"!include"', '"vars"', '"for"', '"!include"', '"vars"', '"for"']
        assert state == JsonlState(0, False)

    def test_a_line_alone_knows_only_the_directive(self):
        assert _kinds('  "!include": "a.jsonl",')[0] == ('"!include"', TokenKind.DIRECTIVE)
        assert _kinds('  "vars": {},')[0] == ('"vars"', TokenKind.KEY)
        assert _kinds('{"!x": 1}')[1] == ('"!x"', TokenKind.DIRECTIVE)
        assert tokenize_jsonl("}}", JsonlState(1, True))[1] == JsonlState(0, False)


class TestPlaceholders(TestBase):
    def test_placeholder_of_a_text_is_a_token(self):
        assert _kinds('{"text": "%ip%"}') == [
            ("{", TokenKind.SYMBOL),
            ('"text"', TokenKind.KEY),
            (":", TokenKind.SYMBOL),
            ('"', TokenKind.STRING),
            ("%ip%", TokenKind.PLACEHOLDER),
            ('"', TokenKind.STRING),
            ("}", TokenKind.SYMBOL),
        ]

    def test_every_known_placeholder_in_any_case(self):
        for name in ("%hostname%", "%ssid%", "%version%", "%model%", "%mac%", "%IP%", "%HostName%"):
            assert (name, TokenKind.PLACEHOLDER) in _kinds(f'  "text": "{name}",')

    def test_only_a_whole_text_is_a_placeholder(self):
        # openHASP doesn't replace a placeholder that is only a part of the text
        assert _kinds('"text": "IP: %ip%"')[-1] == ('"IP: %ip%"', TokenKind.STRING)
        assert _kinds('"text": " %ip%"')[-1] == ('" %ip%"', TokenKind.STRING)

    def test_percent_in_ordinary_text_is_a_string(self):
        assert _kinds('"text": "100%"')[-1] == ('"100%"', TokenKind.STRING)
        assert _kinds('"text": "2:35 / 5:20 | 100%"')[-1] == ('"2:35 / 5:20 | 100%"', TokenKind.STRING)
        assert _kinds('"w": "33%"')[-1] == ('"33%"', TokenKind.STRING)

    def test_unknown_placeholder_is_a_string(self):
        assert _kinds('"text": "%foo%"')[-1] == ('"%foo%"', TokenKind.STRING)

    def test_only_in_the_text(self):
        assert _kinds('"value_str": "%ip%"')[-1] == ('"%ip%"', TokenKind.STRING)
        assert _kinds('"%ip%": 1')[0] == ('"%ip%"', TokenKind.KEY)
        assert _kinds('"text": "%ip%" : 1')[2] == ('"%ip%"', TokenKind.KEY)

    def test_placeholder_inside_a_template_is_part_of_the_template(self):
        assert _kinds('"text": "{{ \'%ip%\' }}"')[2:] == [
            ('"', TokenKind.STRING),
            ("{{ '%ip%' }}", TokenKind.TEMPLATE),
            ('"', TokenKind.STRING),
        ]

    def test_an_unfinished_string_is_no_placeholder(self):
        assert _kinds('"text": "%ip%')[-1] == ('"%ip%', TokenKind.STRING)

    def test_not_in_json_files(self):
        assert _kinds('"text": "%ip%"', Language.JSON)[-1] == ('"%ip%"', TokenKind.STRING)
