import math
from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple

from pfzy.score import fzy_scorer


@dataclass(frozen=True)
class TemplateSuggestion:
    template: str
    value: Any
    # the indices of the characters of the template that matched the query
    positions: Tuple[int, ...]


def template_query(text: str) -> str:
    """:return: what to search for in what was typed into a template field: without the braces and whitespace"""
    return text.replace("{{", "").replace("}}", "").strip()


def filter_template_suggestions(
    query: str,
    suggestions: Sequence[Tuple[str, Any]],
    limit: int = 50,
) -> List[TemplateSuggestion]:
    """
    Fuzzy matches the query against the variables of the suggestions with the fzy algorithm: the characters of the
    query must appear in order, but not necessarily next to each other ("cpmi" matches "common.pages.markus.index"),
    ignoring case. Matches at the start of words and consecutive characters rank higher.

    :param query: the text to search for (see template_query)
    :param suggestions: (template, value), e.g. ("{{ common.pages.markus.index }}", 1)
    :return: the matching suggestions, best first
    """
    matches = []
    for template, value in suggestions:
        # match the variable, not the braces around it
        inner_start = template.find("{{") + 2
        inner = template[inner_start : template.rfind("}}")]
        offset = inner_start + len(inner) - len(inner.lstrip())
        if query:
            score, indices = fzy_scorer(query.lower(), inner.strip())
            if indices is None:
                continue
        else:
            score, indices = -math.inf, []
        matches.append((score, template, value, tuple(offset + index for index in indices)))
    matches.sort(key=lambda m: (-m[0], len(m[1]), m[1]))
    return [
        TemplateSuggestion(template=template, value=value, positions=positions)
        for _, template, value, positions in matches[:limit]
    ]
