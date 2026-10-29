"""
What is wrong with the text of a file while it is typed: an object that is not closed, invalid JSON, a template that
can't be parsed, invalid YAML. This only looks at the text; what the pages make of it (unknown variables, objects outside of
the screen) is `problems.py` and `check.py`.
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, List

import yaml

from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source.objects import pages_of, scan_objects
from openhasp_config_manager.gui.domain.source.syntax import Language, TokenKind, tokenize_line
from openhasp_config_manager.processing.jsonl.includes import directive_error
from openhasp_config_manager.processing.preprocessor.jsonl_preprocessor import OBJECT_START
from openhasp_config_manager.processing.template_rendering import template_syntax_error

_TRAILING_COMMA = re.compile(r",(\s*})")


@dataclass(frozen=True)
class SourceIssue:
    """
    Something to point out in the text of a file: shown in the gutter of the text editor, underlined, and explained on hover.
    Problems the app finds in the objects of a file are shown the same way.
    """

    # starts at 1, like the line numbers of the editor
    line: int
    # starts at 0
    column: int
    length: int
    severity: Severity
    message: str


def find_source_issues(text: str, language: Language) -> List[SourceIssue]:
    """:return: the issues of a text, in the order of the file"""
    issues: List[SourceIssue] = []
    if language == Language.JSONL:
        issues += _jsonl_issues(text)
        issues += _duplicate_id_issues(text)
    elif language == Language.YAML:
        issues += _yaml_issues(text)
    elif language == Language.JSON:
        issues += _json_issues(text)
    issues += _template_issues(text, language)
    return sorted(issues, key=lambda issue: (issue.line, issue.column))


def _jsonl_issues(text: str) -> List[SourceIssue]:
    starts = [match.end() for match in OBJECT_START.finditer(text)]
    issues = []
    # the line of the start of the object before, counted on from there (counting from the start of the text for every object
    # takes seconds in a long file)
    first_line, counted = 1, 0
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        part = text[start:end]
        first_line += text.count("\n", counted, start)
        counted = start
        if "}" not in part:
            issues.append(SourceIssue(first_line, 0, 1, Severity.ERROR, "The object is not closed"))
            continue
        # everything after the last closing bracket is ignored, like a deployment does
        part = part[: part.rindex("}") + 1]
        cleaned = _without_comments_and_trailing_commas(part)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as ex:
            issues.append(
                SourceIssue(first_line + ex.lineno - 1, max(ex.colno - 1, 0), 1, Severity.ERROR, f"Invalid JSON: {ex.msg}")
            )
            continue
        error = directive_error(parsed) if isinstance(parsed, dict) else None
        if error is not None:
            # at the key of the directive (comments are blanked out, so a `"!` in one doesn't count)
            key = cleaned.index('"!')
            position = start + key
            line = first_line + text.count("\n", start, position)
            column = position - (text.rfind("\n", 0, position) + 1)
            length = cleaned.index('"', key + 1) + 1 - key
            issues.append(SourceIssue(line, column, length, Severity.ERROR, error))
    return issues


def _duplicate_id_issues(text: str) -> List[SourceIssue]:
    """The `id` of every object whose id is used by another object on the same page of this text (as written, no templates)."""
    objects = scan_objects(text)
    pages = pages_of(objects)
    users: Dict[tuple, list] = {}
    for obj in objects:
        prop = obj.get("id")
        if prop is None or prop.value is None or "{" in prop.value or "{" in (pages[obj.index] or ""):
            continue
        users.setdefault((pages[obj.index], prop.value), []).append(obj)
    issues = []
    for (_, obj_id), same in users.items():
        for obj in same if len(same) > 1 else []:
            prop = obj.get("id")
            others = ", ".join(str(other.start_line) for other in same if other is not obj)
            issues.append(
                SourceIssue(
                    prop.value_line,
                    prop.value_start,
                    prop.value_end - prop.value_start,
                    Severity.ERROR,
                    f"The id {obj_id} is also used on this page by the object at line {others}",
                )
            )
    return issues


def _without_comments_and_trailing_commas(text: str) -> str:
    """The text the way a deployment parses it, with every character at the same place (for the positions of errors)."""
    lines = []
    for line in text.split("\n"):
        for token in reversed(tokenize_line(line, Language.JSONL)):
            if token.kind == TokenKind.COMMENT:
                line = line[: token.start] + " " * (token.end - token.start)
        lines.append(line)
    return _TRAILING_COMMA.sub(lambda match: " " + match.group(1), "\n".join(lines))


def _yaml_issues(text: str) -> List[SourceIssue]:
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as ex:
        mark = getattr(ex, "problem_mark", None)
        message = getattr(ex, "problem", None) or str(ex)
        if mark is None:
            return [SourceIssue(1, 0, 1, Severity.ERROR, f"Invalid YAML: {message}")]
        return [SourceIssue(mark.line + 1, mark.column, 1, Severity.ERROR, f"Invalid YAML: {message}")]
    return []


def _json_issues(text: str) -> List[SourceIssue]:
    try:
        json.loads(text)
    except json.JSONDecodeError as ex:
        return [SourceIssue(ex.lineno, ex.colno - 1, 1, Severity.ERROR, f"Invalid JSON: {ex.msg}")]
    return []


def _template_issues(text: str, language: Language) -> List[SourceIssue]:
    issues = []
    for number, line in enumerate(text.split("\n"), start=1):
        for token in tokenize_line(line, language):
            if token.kind != TokenKind.TEMPLATE:
                continue
            # only the syntax: the variables are not known here
            error = template_syntax_error(token.text(line))
            if error is not None:
                issues.append(SourceIssue(number, token.start, token.end - token.start, Severity.ERROR, error))
    return issues
