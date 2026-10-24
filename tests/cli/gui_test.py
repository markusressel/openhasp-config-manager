import builtins

from click.testing import CliRunner

from openhasp_config_manager.cli import cli


def test_gui_explains_the_missing_extra(monkeypatch, tmp_path):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PyQt6":
            raise ImportError("No module named 'PyQt6'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = CliRunner().invoke(cli, ["gui", "-c", str(tmp_path)])

    assert result.exit_code != 0
    assert "openhasp-config-manager[gui]" in result.output
