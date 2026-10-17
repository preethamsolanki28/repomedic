import difflib
import fnmatch
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class ConflictError(Exception):
    """Raised when the original repository files were modified concurrently before acceptance."""
    pass


class SecurityTraversalError(Exception):
    """Raised when an operation attempts directory traversal or symlink escape outside the root."""
    pass


EXCLUDED_DIR_NAMES: Set[str] = {
    ".git",
    "node_modules",
    "dist",
    "dist-ssr",
    "build",
    "out",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".pytest_cache",
    ".repomedic",
    ".turbo",
    ".cache",
    "coverage",
    "receipts",
}

EXCLUDED_FILE_PATTERNS: List[str] = [
    ".env*",
    "*.env",
    "credentials*.json",
    "*credentials*.json",
    "*token*.json",
    "*.pem",
    "*.key",
    "*.cert",
    "*.crt",
    "*.p12",
    "*.pfx",
    "*.secret",
    "id_rsa*",
    "id_ed25519*",
    ".DS_Store",
    "thumbs.db",
]


def is_excluded_dir(dir_name: str) -> bool:
    """Check if a directory name matches excluded folder patterns."""
    if dir_name in EXCLUDED_DIR_NAMES:
        return True
    for pattern in EXCLUDED_FILE_PATTERNS:
        if fnmatch.fnmatch(dir_name.lower(), pattern.lower()):
            return True
    return False


def is_excluded_path(rel_path: Path) -> bool:
    """Check if any path segment or the file itself is excluded."""
    # Check parent directory segments
    for part in rel_path.parts[:-1]:
        if is_excluded_dir(part):
            return True
        for pattern in EXCLUDED_FILE_PATTERNS:
            if fnmatch.fnmatch(part.lower(), pattern.lower()):
                return True

    # Check the target file or leaf name
    leaf_name = rel_path.name
    if leaf_name in EXCLUDED_DIR_NAMES:
        return True
    for pattern in EXCLUDED_FILE_PATTERNS:
        if fnmatch.fnmatch(leaf_name.lower(), pattern.lower()):
            return True

    return False


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class WorkspaceManager:
    """Manages isolated temporary workspaces for safe code diagnosis and repair."""

    def __init__(self, temp_prefix: str = "repomedic_ws_"):
        self.temp_prefix = temp_prefix

    def is_safe_symlink(self, path: Path, source_root: Path) -> bool:
        """Check if a symlink resolves strictly within source_root and does not point to excluded files."""
        try:
            resolved = path.resolve()
            source_root_resolved = source_root.resolve()
            if not resolved.is_relative_to(source_root_resolved):
                return False
            rel_target = resolved.relative_to(source_root_resolved)
            if is_excluded_path(rel_target):
                return False
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def create_workspace(self, source_dir: Path | str) -> Tuple[Path, Dict[str, str]]:
        """
        Creates an isolated temporary copy of the source project.
        Excludes secrets, .git, build outputs, and dependencies.
        Returns the workspace directory path and a baseline hash map of copied files.
        """
        source_dir = Path(source_dir).resolve()
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
        if not source_dir.is_dir():
            raise NotADirectoryError(f"Source path is not a directory: {source_dir}")

        temp_dir = Path(tempfile.mkdtemp(prefix=self.temp_prefix))
        baseline: Dict[str, str] = {}

        try:
            for root, dirs, files in os.walk(source_dir, followlinks=False):
                # Filter directories in-place to avoid traversing into excluded trees
                dirs[:] = [d for d in dirs if not is_excluded_dir(d)]

                for f in files:
                    file_path = Path(root) / f
                    rel_path = file_path.relative_to(source_dir)

                    if is_excluded_path(rel_path):
                        continue

                    # Symlink traversal check
                    if file_path.is_symlink():
                        if not self.is_safe_symlink(file_path, source_dir):
                            # Skip unsafe symlinks pointing outside project or to secrets
                            continue

                    dest_path = temp_dir / rel_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                    if file_path.is_symlink():
                        # Copy safe symlink content as regular file
                        shutil.copyfile(file_path.resolve(), dest_path)
                    else:
                        shutil.copy2(file_path, dest_path)

                    baseline[rel_path.as_posix()] = compute_file_hash(dest_path)

        except Exception:
            self.discard_workspace(temp_dir)
            raise

        return temp_dir, baseline

    def compute_diff(self, original_dir: Path | str, workspace_dir: Path | str) -> str:
        """
        Computes a unified diff between the original directory and the workspace.
        Only inspects safe workspace and baseline files; never diffs excluded files.
        """
        original_dir = Path(original_dir).resolve()
        workspace_dir = Path(workspace_dir).resolve()

        # Files in workspace
        ws_files: Set[str] = set()
        for root, _, files in os.walk(workspace_dir):
            for f in files:
                p = Path(root) / f
                ws_files.add(p.relative_to(workspace_dir).as_posix())

        # Permitted files in original
        orig_safe_files: Set[str] = set()
        for root, dirs, files in os.walk(original_dir, followlinks=False):
            dirs[:] = [d for d in dirs if not is_excluded_dir(d)]
            for f in files:
                p = Path(root) / f
                rel = p.relative_to(original_dir)
                if not is_excluded_path(rel):
                    orig_safe_files.add(rel.as_posix())

        all_rel_paths = sorted(ws_files | orig_safe_files)
        diff_lines: List[str] = []

        for rel_path_str in all_rel_paths:
            orig_file = original_dir / rel_path_str
            ws_file = workspace_dir / rel_path_str

            orig_lines: List[str] = []
            if orig_file.exists():
                try:
                    orig_lines = orig_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                except Exception:
                    orig_lines = []

            ws_lines: List[str] = []
            if ws_file.exists():
                try:
                    ws_lines = ws_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                except Exception:
                    ws_lines = []

            if orig_lines != ws_lines:
                diff_lines.extend(
                    difflib.unified_diff(
                        orig_lines,
                        ws_lines,
                        fromfile=f"a/{rel_path_str}",
                        tofile=f"b/{rel_path_str}",
                    )
                )

        return "".join(diff_lines)

    def detect_conflicts(self, original_dir: Path | str, baseline: Dict[str, str]) -> List[str]:
        """
        Checks if any files in original_dir were modified or deleted concurrently since baseline.
        Returns a list of conflicting file paths.
        """
        original_dir = Path(original_dir).resolve()
        conflicts: List[str] = []

        for rel_path_str, expected_hash in baseline.items():
            orig_file = original_dir / rel_path_str
            if not orig_file.exists():
                conflicts.append(rel_path_str)
            else:
                try:
                    current_hash = compute_file_hash(orig_file)
                    if current_hash != expected_hash:
                        conflicts.append(rel_path_str)
                except Exception:
                    conflicts.append(rel_path_str)

        return conflicts

    def apply_changes(
        self,
        original_dir: Path | str,
        workspace_dir: Path | str,
        baseline: Dict[str, str],
    ) -> List[str]:
        """
        Applies changes from workspace to original repository after verifying no conflicts exist.
        Cleans up the temporary workspace after applying.
        Returns the list of modified/added/deleted relative paths.
        """
        conflicts = self.detect_conflicts(original_dir, baseline)
        if conflicts:
            raise ConflictError(
                f"Conflicts detected in original repository: {', '.join(conflicts)}. "
                "Original files were modified concurrently. Aborting apply to protect original."
            )

        original_dir = Path(original_dir).resolve()
        workspace_dir = Path(workspace_dir).resolve()
        applied_files: List[str] = []

        # 1. Apply new or modified files from workspace
        for root, _, files in os.walk(workspace_dir):
            for f in files:
                ws_file = Path(root) / f
                rel_path = ws_file.relative_to(workspace_dir)
                rel_path_str = rel_path.as_posix()

                dest_file = (original_dir / rel_path).resolve()
                if not dest_file.is_relative_to(original_dir):
                    raise SecurityTraversalError(f"Path traversal detected: {rel_path_str}")

                if is_excluded_path(rel_path):
                    continue

                ws_hash = compute_file_hash(ws_file)
                if rel_path_str not in baseline or baseline[rel_path_str] != ws_hash:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ws_file, dest_file)
                    applied_files.append(rel_path_str)

        # 2. Delete files removed from workspace that were in baseline
        for rel_path_str in baseline:
            ws_file = workspace_dir / rel_path_str
            if not ws_file.exists():
                orig_file = (original_dir / rel_path_str).resolve()
                if orig_file.is_relative_to(original_dir) and orig_file.exists():
                    orig_file.unlink()
                    applied_files.append(rel_path_str)

        self.discard_workspace(workspace_dir)
        return applied_files

    def discard_workspace(self, workspace_dir: Path | str) -> None:
        """Securely deletes the temporary workspace directory."""
        ws_path = Path(workspace_dir)
        if ws_path.exists():
            shutil.rmtree(ws_path, ignore_errors=True)
