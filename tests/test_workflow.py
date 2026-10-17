import os
from pathlib import Path
import pytest
from dotenv import load_dotenv

load_dotenv(".env")

from repomedic.workspace import WorkspaceManager
from repomedic.workflow import build_repair_graph, RepairState
from repomedic.security.armoriq_service import ArmorIQService


@pytest.fixture
def workflow_workspace():
    demo_dir = Path("demo").resolve()
    if not demo_dir.exists():
        pytest.skip("demo/ directory not found")

    wm = WorkspaceManager()
    ws_dir, baseline = wm.create_workspace(demo_dir)
    yield ws_dir, demo_dir / "node_modules"
    wm.discard_workspace(ws_dir)


def test_repair_workflow_runs_and_verifies_in_docker(workflow_workspace):
    """Verify LangGraph workflow: Diagnose -> Fix -> Docker Verify -> Complete."""
    ws_dir, node_modules_dir = workflow_workspace

    service = None
    if os.getenv("ARMORIQ_API_KEY") and os.getenv("ARMORIQ_USER_EMAIL"):
        service = ArmorIQService(config_path="armoriq.yaml")

    graph = build_repair_graph(armoriq_service=service)

    initial_state: RepairState = {
        "workspace_dir": str(ws_dir),
        "source_node_modules": str(node_modules_dir),
        "project_name": "repomedic-demo-fixture",
        "pasted_error": None,
        "diagnosis": None,
        "repair_plan": [],
        "approved_files": [],
        "check_results": [],
        "retry_count": 0,
        "armoriq_events": [],
        "security_denial_evidence": None,
        "status": "diagnosing",
    }

    final_state = graph.invoke(initial_state)

    # Must complete successfully
    assert final_state["status"] == "complete"
    assert final_state["retry_count"] <= 2
    assert len(final_state["check_results"]) >= 2

    # All checks must pass
    for check in final_state["check_results"]:
        assert check.passed is True
        assert check.exit_code == 0

    # Must have captured ArmorIQ security proof if service was configured
    if service is not None:
        assert final_state["security_denial_evidence"] is not None
        assert "block" in final_state["security_denial_evidence"].lower() or "deny" in final_state["security_denial_evidence"].lower()


def test_workflow_bounded_retry_honesty(workflow_workspace):
    """Verify workflow stops after 2 retries and reports unresolved errors honestly without faking."""
    ws_dir, node_modules_dir = workflow_workspace

    # Create a mock fixer that refuses to fix the bug to test retry bounding
    class BrokenFixerGraph:
        pass

    graph = build_repair_graph(simulate_unfixable=True)

    initial_state: RepairState = {
        "workspace_dir": str(ws_dir),
        "source_node_modules": str(node_modules_dir),
        "project_name": "repomedic-demo-fixture",
        "pasted_error": None,
        "diagnosis": None,
        "repair_plan": [],
        "approved_files": [],
        "check_results": [],
        "retry_count": 0,
        "armoriq_events": [],
        "security_denial_evidence": None,
        "status": "diagnosing",
    }

    final_state = graph.invoke(initial_state)

    # Must stop and report failed honestly
    assert final_state["status"] == "failed"
    assert final_state["retry_count"] == 2
    assert any(not c.passed for c in final_state["check_results"])
