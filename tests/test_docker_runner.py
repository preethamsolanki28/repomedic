import os
import shutil
import tempfile
from pathlib import Path
import pytest

from repomedic.docker_runner import DockerRunner, CheckResult, DockerUnavailableError
from repomedic.workspace import WorkspaceManager


@pytest.fixture
def temp_demo_workspace():
    """Create an isolated workspace copy of demo/ for docker runner testing."""
    demo_dir = Path("demo").resolve()
    if not demo_dir.exists():
        pytest.skip("demo/ directory not found")

    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(demo_dir)
    yield ws_dir, demo_dir / "node_modules"
    wm.discard_workspace(ws_dir)


def test_docker_runner_fails_on_broken_fixture(temp_demo_workspace):
    """Verify docker runner executes checks in Docker with network none and reports seeded failures."""
    ws_dir, node_modules_dir = temp_demo_workspace
    runner = DockerRunner()

    results = runner.run_checks(ws_dir, source_node_modules=node_modules_dir)
    assert len(results) == 2

    type_check = next((r for r in results if r.name == "check:type"), None)
    test_check = next((r for r in results if r.name == "test"), None)

    assert type_check is not None
    assert type_check.passed is False
    assert type_check.exit_code != 0
    assert "TS2322" in (type_check.stdout + type_check.stderr)

    assert test_check is not None
    assert test_check.passed is False
    assert test_check.exit_code != 0
    assert "FAIL" in (test_check.stdout + test_check.stderr)


def test_docker_runner_passes_on_fixed_fixture(temp_demo_workspace):
    """Verify docker runner passes both checks when seeded bugs are fixed in workspace."""
    ws_dir, node_modules_dir = temp_demo_workspace

    # Fix Bug 1: App.tsx
    app_tsx = ws_dir / "src" / "App.tsx"
    app_content = app_tsx.read_text()
    fixed_app = app_content.replace('initialCount="0"', 'initialCount={0}')
    app_tsx.write_text(fixed_app)

    # Fix Bug 2: Counter.tsx
    counter_tsx = ws_dir / "src" / "Counter.tsx"
    counter_content = counter_tsx.read_text()
    fixed_counter = counter_content.replace(
        'setCount(count - 1)',
        'setCount(count + 1)',
    )
    counter_tsx.write_text(fixed_counter)

    runner = DockerRunner()
    results = runner.run_checks(ws_dir, source_node_modules=node_modules_dir)

    type_check = next((r for r in results if r.name == "check:type"), None)
    test_check = next((r for r in results if r.name == "test"), None)

    assert type_check is not None
    assert type_check.passed is True
    assert type_check.exit_code == 0

    assert test_check is not None
    assert test_check.passed is True
    assert test_check.exit_code == 0
