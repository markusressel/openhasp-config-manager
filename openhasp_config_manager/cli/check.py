import json
from pathlib import Path
from typing import Optional

import click

from openhasp_config_manager.check import check_config
from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.problems import Severity


def c_check(config_dir: Path, device: Optional[str], as_json: bool) -> bool:
    """
    Print what is wrong with the config directory.
    :return: whether there are no errors (warnings are fine)
    """
    # nothing is written: the output directory is only needed by the manager
    config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
    devices, issues = check_config(config_manager, device)
    ok = not any(issue.severity == Severity.ERROR for issue in issues)

    if as_json:
        click.echo(json.dumps({"ok": ok, "devices": devices, "issues": [issue.to_dict() for issue in issues]}, indent=2))
        return ok

    for issue in issues:
        click.echo(str(issue))
    errors = sum(issue.severity == Severity.ERROR for issue in issues)
    hints = sum(issue.severity == Severity.HINT for issue in issues)
    warnings = len(issues) - errors - hints
    summary = (
        f"Checked {len(devices)} device{'' if len(devices) == 1 else 's'}: {errors} error{'' if errors == 1 else 's'}, "
        f"{warnings} warning{'' if warnings == 1 else 's'}"
    )
    click.echo(summary + (f", {hints} hint{'' if hints == 1 else 's'}" if hints else ""))
    return ok
