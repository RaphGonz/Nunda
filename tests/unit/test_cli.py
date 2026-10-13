from typer.testing import CliRunner

from ccm.cli import app


def test_aide():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CCM" in result.output
