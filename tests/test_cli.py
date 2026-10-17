import shutil
import tempfile
from pathlib import Path
import pytest
from typer.testing import CliRunner
from repomedic.cli import app

runner = CliRunner()


@pytest.fixture
def cli_sample_project():
    temp_dir = tempfile.mkdtemp(prefix="repomedic_cli_test_")
    proj = Path(temp_dir)
    (proj / "src").mkdir()
    (proj / "src" / "App.tsx").write_text("const x: string = 'broken';\n")
    (proj / "package.json").write_text('{"name": "cli-demo"}\n')
    (proj / ".env").write_text("API_SECRET=private123\n")

    yield proj

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


import os


def test_cli_help():
    """Verify CLI help display."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "repomedic" in result.output.lower() or "repair" in result.output.lower()


def test_cli_fix_help():
    """Verify `repomedic fix --help` display."""
    result = runner.invoke(app, ["fix", "--help"])
    assert result.exit_code == 0
    assert "fix" in result.output.lower()


def test_cli_fix_reject_workflow(cli_sample_project):
    """Verify rejecting a fix leaves original file untouched."""
    original_text = (cli_sample_project / "src" / "App.tsx").read_text()

    result = runner.invoke(
        app,
        ["fix", str(cli_sample_project), "--no-prompt-error", "--reject"],
    )

    assert result.exit_code == 0
    assert "rejected" in result.output.lower() or "discard" in result.output.lower()
    # Original content must be identical
    assert (cli_sample_project / "src" / "App.tsx").read_text() == original_text
    # Secret must still exist in original
    assert (cli_sample_project / ".env").exists()


def test_cli_fix_accept_workflow(cli_sample_project):
    """Verify accepting applies patch when a diff is present."""
    result = runner.invoke(
        app,
        ["fix", str(cli_sample_project), "--error", "TypeError: build error", "--accept"],
    )

    assert result.exit_code == 0
    assert (cli_sample_project / ".env").exists()


def test_cli_version():
    """Verify CLI --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "repomedic" in result.output.lower()
    assert "0.1.0" in result.output


def test_cli_fix_nonexistent_path():
    """Verify fix command handles nonexistent directory gracefully."""
    result = runner.invoke(app, ["fix", "/non/existent/path/for/repomedic/test", "--no-prompt-error"])
    assert result.exit_code == 1
    assert "not exist" in result.output.lower()


def test_cli_fix_file_instead_of_directory(cli_sample_project):
    """Verify fix command handles file path instead of directory gracefully."""
    target_file = cli_sample_project / "src" / "App.tsx"
    result = runner.invoke(app, ["fix", str(target_file), "--no-prompt-error"])
    assert result.exit_code == 1
    assert "not a directory" in result.output.lower()


def test_cli_fix_interactive_error_prompt(cli_sample_project):
    """Verify interactive error prompt accepts input."""
    result = runner.invoke(
        app,
        ["fix", str(cli_sample_project), "--reject"],
        input="TS2322: Type 'number' is not assignable\n",
    )
    assert result.exit_code == 0
    assert "diagnostic hint received" in result.output.lower()

