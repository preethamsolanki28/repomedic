import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


class DockerUnavailableError(Exception):
    """Raised when Docker daemon or command is unavailable."""
    pass


@dataclass(frozen=True)
class CheckResult:
    """Structured result of a project verification check run inside Docker."""
    name: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool


class DockerRunner:
    """Runs project build and test checks inside an isolated Docker container with network disabled."""

    def __init__(self, image: str = "node:22-slim"):
        self.image = image

    def is_docker_available(self) -> bool:
        """Check if Docker CLI and daemon are responding."""
        if not shutil.which("docker"):
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return res.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def run_single_check(
        self,
        name: str,
        cmd: List[str],
        workspace_dir: Path,
        source_node_modules: Optional[Path] = None,
        timeout: int = 60,
    ) -> CheckResult:
        """Executes a single check command inside Docker without network access."""
        if not self.is_docker_available():
            raise DockerUnavailableError("Docker is not running or not installed.")

        workspace_dir = Path(workspace_dir).resolve()

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{workspace_dir}:/app:rw",
        ]

        if source_node_modules and Path(source_node_modules).exists():
            clean_nm = Path(source_node_modules).resolve()
            docker_cmd.extend([
                "-v",
                f"{clean_nm}:/app/node_modules:ro",
                "--tmpfs",
                "/app/node_modules/.vite",
            ])

        docker_cmd.extend([
            "-w",
            "/app",
            "-e",
            "CI=true",
            "-e",
            "NODE_ENV=test",
            self.image,
        ])
        docker_cmd.extend(cmd)

        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return CheckResult(
                name=name,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                passed=(proc.returncode == 0),
            )
        except subprocess.TimeoutExpired as exc:
            return CheckResult(
                name=name,
                exit_code=-1,
                stdout=exc.stdout or "",
                stderr=f"Command timed out after {timeout} seconds",
                passed=False,
            )
        except Exception as exc:
            return CheckResult(
                name=name,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                passed=False,
            )

    def run_checks(
        self,
        workspace_dir: Path,
        source_node_modules: Optional[Path] = None,
        timeout: int = 60,
    ) -> List[CheckResult]:
        """Runs standard React/Vite checks: npm run check:type and npm test."""
        results = []

        # 1. TypeScript build check
        type_check = self.run_single_check(
            name="check:type",
            cmd=["npm", "run", "check:type"],
            workspace_dir=workspace_dir,
            source_node_modules=source_node_modules,
            timeout=timeout,
        )
        results.append(type_check)

        # 2. Vitest unit tests
        test_check = self.run_single_check(
            name="test",
            cmd=["npm", "test"],
            workspace_dir=workspace_dir,
            source_node_modules=source_node_modules,
            timeout=timeout,
        )
        results.append(test_check)

        return results
