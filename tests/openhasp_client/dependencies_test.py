import subprocess
import sys

# what only the CLI and the GUI (the `gui` extra) need: haad and AppDaemon use the client without them
CLI_AND_GUI_MODULES = (
    "click",
    "PyQt6",
    "qtawesome",
    "qt_themes",
    "pfzy",
    "watchdog",
    "segno",
    "openhasp_config_manager.console",
    "openhasp_config_manager.cli",
    "openhasp_config_manager.gui",
)


class TestClientDependencies:
    def test_the_client_needs_neither_cli_nor_gui(self):
        code = (
            "import sys, openhasp_config_manager.openhasp_client.openhasp; "
            f"print(sorted(n for n in sys.modules if n.split('.')[0] in {CLI_AND_GUI_MODULES!r} or n.startswith({CLI_AND_GUI_MODULES!r})))"
        )
        assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip() == "[]"
