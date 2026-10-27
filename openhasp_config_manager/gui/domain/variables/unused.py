"""The variables of the YAML files that no file of any device uses, as hints for the text editor (see `VariableUsages`). Qt-free."""

from dataclasses import dataclass
from typing import Dict, List
from pathlib import Path

from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source.issues import SourceIssue
from openhasp_config_manager.gui.domain.variables.usages import VariableUsages


@dataclass(frozen=True)
class UnusedVariables:
    """The unused variables of a YAML file, and the text of the file they were found in (their lines are only right for that)."""

    content: str
    issues: List[SourceIssue]


def find_unused_variables(usages: VariableUsages) -> Dict[Path, UnusedVariables]:
    """:return: the YAML files that have unused variables (resolved paths)"""
    result = {}
    for variable_file, leaves in usages.unused().items():
        content = variable_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        result[variable_file] = UnusedVariables(
            content,
            [
                SourceIssue(
                    leaf.line,
                    leaf.column,
                    max(len(lines[leaf.line - 1].rstrip()) - leaf.column, 1),
                    Severity.HINT,
                    f"Not used: no file of any device uses {leaf.name}",
                )
                for leaf in leaves
            ],
        )
    return result
