"""
What is wrong with the text of a file while it is typed: an object that is not closed, invalid JSON, a template that
can't be parsed, invalid YAML. This only looks at the text; what the pages make of it (unknown variables, objects outside of
the screen) is `problems.py` and `check.py`.
"""

import json
import re
from dataclasses import dataclass
from typing import List

import yaml

from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source_syntax import Language, TokenKind, tokenize_line
from openhasp_config_manager.processing.template_rendering import check_template

_OBJECT_START = re.compile(r"^(?!\n)\s*(?=\{)", re.MULTILINE)
_TRAILING_COMMA = re.compile(r",(\s*})")
_INVALID_TEMPLATE = "Invalid template"


@dataclass(frozen=True)
class SourceIssue:
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
    elif language == Language.YAML:
        issues += _yaml_issues(text)
    issues += _template_issues(text, language)
    return sorted(issues, key=lambda issue: (issue.line, issue.column))


def _jsonl_issues(text: str) -> List[SourceIssue]:
    starts = [match.end() for match in _OBJECT_START.finditer(text)]
    issues = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        part = text[start:end]
        first_line = text.count("\n", 0, start) + 1
        if "}" not in part:
            issues.append(SourceIssue(first_line, 0, 1, Severity.ERROR, "The object is not closed"))
            continue
        # everything after the last closing bracket is ignored, like a deployment does
        part = part[: part.rindex("}") + 1]
        try:
            json.loads(_without_comments_and_trailing_commas(part))
        except json.JSONDecodeError as ex:
            issues.append(
                SourceIssue(first_line + ex.lineno - 1, max(ex.colno - 1, 0), 1, Severity.ERROR, f"Invalid JSON: {ex.msg}")
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


def _template_issues(text: str, language: Language) -> List[SourceIssue]:
    issues = []
    for number, line in enumerate(text.split("\n"), start=1):
        for token in tokenize_line(line, language):
            if token.kind != TokenKind.TEMPLATE:
                continue
            # only the syntax: the variables are not known here
            error = check_template(token.text(line), {})
            if error is not None and error.startswith(_INVALID_TEMPLATE):
                issues.append(SourceIssue(number, token.start, token.end - token.start, Severity.ERROR, error))
    return issues
