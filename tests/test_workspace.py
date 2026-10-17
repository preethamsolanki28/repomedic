import os
import shutil
import tempfile
from pathlib import Path
import pytest
from repomedic.workspace import (
    WorkspaceManager,
    ConflictError,
    SecurityTraversalError,
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="repomedic_test_")
    yield Path(d)
    if os.path.exists(d):
        shutil.rmtree(d)


@pytest.fixture
def sample_project(temp_dir):
    project_dir = temp_dir / "my_project"
    project_dir.mkdir()

    # Safe source files
    (project_dir / "src").mkdir()
    (project_dir / "src" / "App.tsx").write_text("const a: string = 'hello';\n")
    (project_dir / "package.json").write_text('{"name": "test"}\n')

    # Excluded files and directories
    (project_dir / ".env").write_text("SECRET_KEY=12345\n")
    (project_dir / ".env.local").write_text("API_KEY=67890\n")
    (project_dir / "credentials.json").write_text('{"token": "xyz"}\n')
    (project_dir / "auth_token.json").write_text('{"jwt": "abc"}\n')
    (project_dir / "server.key").write_text("PRIVATE_KEY\n")

    # Excluded directories
    (project_dir / ".git").mkdir()
    (project_dir / ".git" / "config").write_text("[core]\n")

    (project_dir / "node_modules").mkdir()
    (project_dir / "node_modules" / "pkg.js").write_text("module.exports = {};\n")

    (project_dir / "dist").mkdir()
    (project_dir / "dist" / "bundle.js").write_text("bundled\n")

    return project_dir


def test_workspace_copy_excludes_secrets_git_dependencies(sample_project):
    """Verify that temporary workspace copies safe files and strictly excludes secrets and dependencies."""
    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(sample_project)

    try:
        # Permitted files must exist
        assert (ws_dir / "src" / "App.tsx").exists()
        assert (ws_dir / "package.json").exists()

        # Excluded secrets must NOT exist
        assert not (ws_dir / ".env").exists()
        assert not (ws_dir / ".env.local").exists()
        assert not (ws_dir / "credentials.json").exists()
        assert not (ws_dir / "auth_token.json").exists()
        assert not (ws_dir / "server.key").exists()

        # Excluded directories must NOT exist
        assert not (ws_dir / ".git").exists()
        assert not (ws_dir / "node_modules").exists()
        assert not (ws_dir / "dist").exists()

        # Baseline snapshot must track copied files
        assert "src/App.tsx" in baseline
        assert "package.json" in baseline
        assert ".env" not in baseline
    finally:
        wm.discard_workspace(ws_dir)


def test_workspace_rejects_symlink_traversal(sample_project, temp_dir):
    """Verify symlinks pointing outside the project root are rejected or skipped."""
    outside_file = temp_dir / "outside_secret.txt"
    outside_file.write_text("SENSITIVE_HOST_INFO\n")

    # Create symlink pointing outside
    symlink_path = sample_project / "src" / "escaped_link.txt"
    try:
        os.symlink(outside_file, symlink_path)
    except OSError:
        pytest.skip("Symlink creation not permitted in this environment")

    wm = WorkspaceManager()
    ws_dir, _ = wm.create_workspace(sample_project)

    try:
        # The escaped link must NOT resolve to outside file in workspace
        copied_link = ws_dir / "src" / "escaped_link.txt"
        assert not copied_link.exists() or not copied_link.is_symlink()
    finally:
        wm.discard_workspace(ws_dir)


def test_compute_diff(sample_project):
    """Verify diff computation accurately detects modifications."""
    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(sample_project)

    try:
        # Modify a file in workspace
        (ws_dir / "src" / "App.tsx").write_text("const a: number = 42;\n")

        diff = wm.compute_diff(sample_project, ws_dir)
        assert "-const a: string = 'hello';" in diff
        assert "+const a: number = 42;" in diff
    finally:
        wm.discard_workspace(ws_dir)


def test_discard_workspace_leaves_original_untouched(sample_project):
    """Verify rejection deletes workspace and leaves original completely untouched."""
    wm = WorkspaceManager()
    ws_dir, _ = wm.create_workspace(sample_project)

    original_content = (sample_project / "src" / "App.tsx").read_text()

    # Modify workspace
    (ws_dir / "src" / "App.tsx").write_text("CHANGED CONTENT\n")
    (ws_dir / "src" / "NewFile.tsx").write_text("NEW CONTENT\n")

    wm.discard_workspace(ws_dir)

    # Workspace directory removed
    assert not ws_dir.exists()

    # Original files completely untouched
    assert (sample_project / "src" / "App.tsx").read_text() == original_content
    assert not (sample_project / "src" / "NewFile.tsx").exists()


def test_apply_changes_updates_original(sample_project):
    """Verify accept applies only the reviewed changes from workspace to original."""
    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(sample_project)

    # Make change
    (ws_dir / "src" / "App.tsx").write_text("const a: number = 100;\n")

    diff = wm.compute_diff(sample_project, ws_dir)
    assert len(diff) > 0

    applied_files = wm.apply_changes(sample_project, ws_dir, baseline)
    assert "src/App.tsx" in applied_files

    # Original file is updated
    assert (sample_project / "src" / "App.tsx").read_text() == "const a: number = 100;\n"

    # Workspace is cleaned up
    assert not ws_dir.exists()


def test_conflict_detection_when_original_modified(sample_project):
    """Verify conflict detection when original is modified concurrently before acceptance."""
    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(sample_project)

    try:
        # Modify workspace
        (ws_dir / "src" / "App.tsx").write_text("WORKSPACE FIX\n")

        # Concurrently modify original file
        (sample_project / "src" / "App.tsx").write_text("CONCURRENT USER EDIT\n")

        # Attempting apply must raise ConflictError
        with pytest.raises(ConflictError) as exc_info:
            wm.apply_changes(sample_project, ws_dir, baseline)

        assert "src/App.tsx" in str(exc_info.value)

        # Original edit must NOT be overwritten
        assert (sample_project / "src" / "App.tsx").read_text() == "CONCURRENT USER EDIT\n"
    finally:
        wm.discard_workspace(ws_dir)


def test_support_non_git_folder(sample_project):
    """Verify non-git folders work seamlessly without git dependence."""
    # Remove .git folder entirely
    shutil.rmtree(sample_project / ".git")
    assert not (sample_project / ".git").exists()

    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(sample_project)

    (ws_dir / "src" / "App.tsx").write_text("NON_GIT_FIX\n")
    wm.apply_changes(sample_project, ws_dir, baseline)

    assert (sample_project / "src" / "App.tsx").read_text() == "NON_GIT_FIX\n"


def test_nested_secrets_and_build_outputs_excluded(sample_project):
    """Verify secrets and outputs nested deeply within subdirectories are excluded."""
    nested_dir = sample_project / "src" / "components" / "config"
    nested_dir.mkdir(parents=True)
    (nested_dir / ".env.production").write_text("PROD_SECRET=999\n")
    (nested_dir / "service_account_credentials.json").write_text('{"key": "val"}\n')
    (nested_dir / "safe_component.tsx").write_text("export const Safe = () => null;\n")

    nested_build = sample_project / "packages" / "ui" / "build"
    nested_build.mkdir(parents=True)
    (nested_build / "bundle.js").write_text("bundled output\n")

    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(sample_project)

    try:
        assert (ws_dir / "src" / "components" / "config" / "safe_component.tsx").exists()
        assert not (ws_dir / "src" / "components" / "config" / ".env.production").exists()
        assert not (ws_dir / "src" / "components" / "config" / "service_account_credentials.json").exists()
        assert not (ws_dir / "packages" / "ui" / "build").exists()
    finally:
        wm.discard_workspace(ws_dir)


def test_apply_new_and_deleted_files(sample_project):
    """Verify adding a new file and deleting an existing file in workspace applies correctly."""
    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(sample_project)

    # 1. Add a new file in workspace
    (ws_dir / "src" / "NewUtil.ts").write_text("export const util = 1;\n")
    # 2. Delete an existing file in workspace
    (ws_dir / "package.json").unlink()

    diff = wm.compute_diff(sample_project, ws_dir)
    assert "+export const util = 1;" in diff
    assert '-{"name": "test"}' in diff

    applied = wm.apply_changes(sample_project, ws_dir, baseline)
    assert "src/NewUtil.ts" in applied
    assert "package.json" in applied

    # Check original
    assert (sample_project / "src" / "NewUtil.ts").read_text() == "export const util = 1;\n"
    assert not (sample_project / "package.json").exists()

