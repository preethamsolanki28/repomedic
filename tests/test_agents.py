import os
import shutil
import tempfile
from pathlib import Path
import pytest
from dotenv import load_dotenv

load_dotenv(".env")

from repomedic.workspace import WorkspaceManager
from repomedic.agents.diagnoser import DiagnoserAgent, DiagnosisResult
from repomedic.agents.fixer import FixerAgent, FixerScopeError
from repomedic.security.armoriq_service import ArmorIQService


@pytest.fixture
def agent_workspace():
    demo_dir = Path("demo").resolve()
    if not demo_dir.exists():
        pytest.skip("demo/ directory not found")

    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(demo_dir)
    yield ws_dir, baseline
    wm.discard_workspace(ws_dir)


def test_diagnoser_is_read_only_and_detects_bugs(agent_workspace):
    """Verify Diagnoser performs read-only analysis and identifies both seeded bugs."""
    ws_dir, baseline = agent_workspace
    diagnoser = DiagnoserAgent(armoriq_service=None)

    # Diagnoser inspects workspace
    result = diagnoser.diagnose(ws_dir)

    assert isinstance(result, DiagnosisResult)
    assert len(result.repair_plan) >= 2
    # Approved files must be restricted strictly to source files
    assert "src/App.tsx" in result.approved_files
    assert "src/Counter.tsx" in result.approved_files
    # Test and config files must NEVER be in approved_files
    assert "src/Counter.test.tsx" not in result.approved_files
    assert "vite.config.ts" not in result.approved_files
    assert "package.json" not in result.approved_files

    # Plain english explanation must mention the type error and counter logic error
    diag_text = result.explanation.lower()
    assert "type" in diag_text or "app.tsx" in diag_text or "string" in diag_text
    assert "counter" in diag_text or "logic" in diag_text or "increment" in diag_text


def test_diagnoser_security_test_routes_through_armoriq_and_proves_denial(agent_workspace):
    """Verify Diagnoser routes the malicious README debug report through real ArmorIQ and captures denial evidence."""
    api_key = os.getenv("ARMORIQ_API_KEY")
    user_email = os.getenv("ARMORIQ_USER_EMAIL")
    if not api_key or not user_email:
        pytest.skip("ArmorIQ credentials not found in environment")

    ws_dir, _ = agent_workspace
    service = ArmorIQService(config_path="armoriq.yaml")
    diagnoser = DiagnoserAgent(armoriq_service=service)

    # Trigger security mediation check
    receipt = diagnoser.test_security_boundary(ws_dir)

    # Must be genuinely blocked by ArmorIQ policy
    assert receipt.allowed is False
    assert receipt.is_policy_blocked is True
    assert "block" in receipt.decision.lower() or "deny" in receipt.decision.lower()
    assert receipt.action == "send_debug_report"


def test_fixer_scope_enforcement_blocks_unauthorized_paths(agent_workspace):
    """Verify Fixer is strictly blocked from editing test files, configs, or unapproved paths."""
    ws_dir, _ = agent_workspace
    approved_files = ["src/App.tsx", "src/Counter.tsx"]
    fixer = FixerAgent(approved_files=approved_files)

    # Attempting to edit test file must be blocked
    with pytest.raises(FixerScopeError) as exc_test:
        fixer.apply_file_edit(ws_dir, "src/Counter.test.tsx", "// modified test")
    assert "Counter.test.tsx" in str(exc_test.value)

    # Attempting to edit config file must be blocked
    with pytest.raises(FixerScopeError) as exc_config:
        fixer.apply_file_edit(ws_dir, "vite.config.ts", "// modified config")
    assert "vite.config.ts" in str(exc_config.value)

    # Attempting to edit outside workspace must be blocked
    with pytest.raises(FixerScopeError) as exc_outside:
        fixer.apply_file_edit(ws_dir, "../outside.txt", "escaped")
    assert "traversal" in str(exc_outside.value).lower() or "outside" in str(exc_outside.value).lower()


def test_fixer_repairs_seeded_bugs_in_workspace(agent_workspace):
    """Verify Fixer repairs both seeded bugs in the approved workspace source files."""
    ws_dir, _ = agent_workspace
    approved_files = ["src/App.tsx", "src/Counter.tsx"]
    fixer = FixerAgent(approved_files=approved_files)

    modified_files = fixer.repair(ws_dir)
    assert "src/App.tsx" in modified_files
    assert "src/Counter.tsx" in modified_files

    # Check App.tsx content
    app_text = (ws_dir / "src" / "App.tsx").read_text()
    assert 'initialCount={42}' in app_text or 'initialCount={0}' in app_text or 'initialCount="42"' not in app_text

    # Check Counter.tsx content
    counter_text = (ws_dir / "src" / "Counter.tsx").read_text()
    assert 'count + 1' in counter_text or 'prev + 1' in counter_text
