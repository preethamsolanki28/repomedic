import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from armoriq_sdk import (
    ArmorIQClient,
    IntentMismatchException,
    IntentToken,
    MCPInvocationResult,
    PlanCapture,
    PolicyBlockedException,
    PolicyHoldException,
)
from armoriq_sdk.config import load_armoriq_config, resolve_env_reference

logger = logging.getLogger("repomedic.security")


@dataclass(frozen=True)
class InvocationReceipt:
    """Documented receipt capturing ArmorIQ mediation evidence without leaking secrets."""
    allowed: bool
    decision: str
    action: str
    mcp: str
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    data: Optional[Any] = None
    execution_time: Optional[float] = None
    is_policy_blocked: bool = False
    is_intent_mismatch: bool = False


class ArmorIQService:
    """Service wrapping ArmorIQ SDK operations for RepoMedic agents."""

    def __init__(self, client: Optional[ArmorIQClient] = None, config_path: str = "armoriq.yaml"):
        if client:
            self.client = client
        else:
            config = load_armoriq_config(config_path)
            mcp_creds = {}
            for s in config.mcp_servers:
                if s.auth.type == "bearer":
                    t = resolve_env_reference(s.auth.token or "")
                    mcp_creds[s.id] = {"authType": "bearer", "token": t}
                    mcp_creds[s.id.upper().replace("-", "_")] = {"authType": "bearer", "token": t}
            self.client = ArmorIQClient(
                api_key=config.identity.resolved_api_key(),
                user_id=resolve_env_reference(config.identity.user_id),
                agent_id=config.identity.agent_id,
                proxy_endpoint=config.proxy.url,
                timeout=float(config.proxy.timeout),
                max_retries=int(config.proxy.max_retries),
                use_production=(config.environment == "production"),
                mcp_credentials=mcp_creds,
            )

    def capture_repair_plan(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
        llm: str = "devstral-small-2",
        prompt: str = "Plan repair steps",
    ) -> PlanCapture:
        """Capture an agent's intended execution plan."""
        plan_dict = {
            "goal": goal,
            "steps": steps,
        }
        return self.client.capture_plan(llm=llm, prompt=prompt, plan=plan_dict)

    def mint_intent_token(
        self,
        captured_plan: PlanCapture,
        validity_seconds: float = 300.0,
    ) -> IntentToken:
        """Mint a cryptographically signed intent token from CSRG-IAP."""
        return self.client.get_intent_token(
            captured_plan,
            validity_seconds=validity_seconds,
        )

    def invoke_protected_tool(
        self,
        mcp: str,
        action: str,
        intent_token: IntentToken,
        params: Optional[Dict[str, Any]] = None,
        user_email: Optional[str] = None,
    ) -> InvocationReceipt:
        """
        Execute an MCP action through the ArmorIQ proxy.
        Distinguishes policy denials (PolicyBlockedException) from intent mismatches (IntentMismatchException).
        Fails closed on enforcement errors.
        """
        clean_params = self._sanitize_params(params or {})

        try:
            result: MCPInvocationResult = self.client.invoke(
                mcp=mcp,
                action=action,
                intent_token=intent_token,
                params=clean_params,
                user_email=user_email,
            )
            return InvocationReceipt(
                allowed=True,
                decision="allow",
                action=action,
                mcp=mcp,
                data=result.result,
                metadata=result.metadata or {},
                execution_time=result.execution_time,
                is_policy_blocked=False,
                is_intent_mismatch=False,
            )
        except PolicyBlockedException as exc:
            logger.warning(
                "ArmorIQ PDP policy denial: action=%s, decision=%s, reason=%s",
                action,
                exc.enforcement_action,
                exc.reason,
            )
            return InvocationReceipt(
                allowed=False,
                decision=exc.enforcement_action or "deny",
                action=action,
                mcp=mcp,
                reason=exc.reason,
                metadata=exc.metadata or {},
                is_policy_blocked=True,
                is_intent_mismatch=False,
            )
        except IntentMismatchException as exc:
            logger.error("ArmorIQ intent mismatch / drift: action=%s, plan_hash=%s", exc.action, exc.plan_hash)
            return InvocationReceipt(
                allowed=False,
                decision="intent_mismatch",
                action=action,
                mcp=mcp,
                reason=str(exc),
                is_policy_blocked=False,
                is_intent_mismatch=True,
            )
        except PolicyHoldException as exc:
            logger.info("ArmorIQ policy hold for approval: action=%s", action)
            return InvocationReceipt(
                allowed=False,
                decision="hold",
                action=action,
                mcp=mcp,
                reason=str(exc),
                metadata=exc.metadata or {},
                is_policy_blocked=False,
                is_intent_mismatch=False,
            )

    def invoke_repair_action(
        self,
        action: str,
        mcp: str = "repomedic-mcp",
        params: Optional[Dict[str, Any]] = None,
        goal: Optional[str] = None,
    ) -> InvocationReceipt:
        """Convenience method to capture plan, mint token, and invoke protected tool through ArmorIQ."""
        step_goal = goal or f"Execute repair action: {action}"
        plan = self.capture_repair_plan(
            goal=step_goal,
            steps=[{"action": action, "mcp": mcp, "params": params or {}}],
        )
        token = self.mint_intent_token(plan)
        return self.invoke_protected_tool(
            mcp=mcp,
            action=action,
            intent_token=token,
            params=params,
        )

    @staticmethod
    def _sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
        """Redact known secret patterns to prevent accidental leakage in telemetry."""
        sanitized = {}
        for k, v in params.items():
            if any(secret_word in k.lower() for secret_word in ["secret", "token", "password", "key"]):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = ArmorIQService._sanitize_params(v)
            else:
                sanitized[k] = v
        return sanitized
