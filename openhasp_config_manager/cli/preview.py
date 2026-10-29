import os
import sys
from pathlib import Path
from typing import Optional, Sequence

import click

from openhasp_config_manager.cli.common import _create_config_manager

# the folder in the state folder of the config directory the images go into, if no other is given
PREVIEW_DIR_NAME = "preview"

_APP = None


def c_preview(
    config_dir: Path, device: Optional[str], pages: Sequence[int], output_dir: Optional[Path], scale: float
) -> bool:
    """
    Render pages of the devices like the preview of the GUI shows them, from the files on disk, into `<device>/page_<n>.png`.
    :param pages: the pages to render, all pages with objects if empty
    :param output_dir: where the images go, the state folder of the GUI in the config directory by default
    :return: whether all devices could be rendered
    """
    # headless: no window is shown
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    global _APP
    # kept for the rest of the process: Qt objects created meanwhile (e.g. the bridge of `async_bridge`) stop getting
    # their events if the application is destroyed
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

    from openhasp_config_manager.gui.domain.draft.files import load_device
    from openhasp_config_manager.gui.domain.draft.session import PlateSession
    from openhasp_config_manager.gui.domain.gui_state import ensure_state_folder
    from openhasp_config_manager.gui.qt.preview_image import png_bytes, render_pages

    # nothing is written there: the output directory is only needed by the manager
    config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
    names = [d.name for d in sorted(config_manager.analyze(), key=lambda d: d.name)]
    if device is not None:
        if device not in names:
            click.echo(f"No device named '{device}', found: {', '.join(names)}", err=True)
            return False
        names = [device]
    if output_dir is None:
        output_dir = ensure_state_folder(Path(config_dir)) / PREVIEW_DIR_NAME

    ok = True
    for name in names:
        try:
            loaded = load_device(config_manager, name)
            session = PlateSession(device=loaded.device)
            session.load(loaded.components, loaded.renderer)
            images = render_pages(session, loaded.device, pages or None, scale)
        except Exception as ex:
            click.echo(f"{name}: can't be rendered: {ex}", err=True)
            ok = False
            continue
        folder = output_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        if not pages:
            # all pages: no image of a page that has no objects anymore
            for stale in folder.glob("page_*.png"):
                stale.unlink()
        for page, image in images.items():
            path = folder / f"page_{page}.png"
            path.write_bytes(png_bytes(image))
            click.echo(str(path))
    _APP.processEvents()
    return ok
