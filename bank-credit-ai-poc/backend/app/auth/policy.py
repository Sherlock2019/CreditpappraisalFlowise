"""Default-deny authorization policy: roles map to explicit permissions; anything unlisted is denied."""
from __future__ import annotations

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "loan_officer": frozenset(
        {"customer:read", "evidence:read", "agent:execute", "agent_run:read", "approval:read", "approval:decide"}
    ),
    "credit_analyst": frozenset({"customer:read", "evidence:read", "agent:execute", "agent_run:read", "approval:read"}),
    "asset_analyst": frozenset({"customer:read", "evidence:read", "agent_run:read", "approval:read"}),
    "fraud_analyst": frozenset({"customer:read", "evidence:read", "agent_run:read", "audit:read"}),
    "compliance_officer": frozenset({"customer:read", "agent_run:read", "approval:read", "audit:read", "audit:verify"}),
    "tenant_admin": frozenset({"tenant:admin", "agent_run:read", "audit:read", "audit:verify"}),
    # Platform operators manage the system, not tenant data: no customer, evidence or decision access.
    "platform_admin": frozenset({"platform:admin", "audit:verify"}),
    # Agent permissions come only from agent_permissions.json, never from a human role.
    "ai_agent_runtime": frozenset(),
}

# Permissions that only an authenticated human may ever hold.
HUMAN_ONLY_PERMISSIONS = frozenset({"approval:decide", "agent:execute"})


def permissions_for_roles(roles: set[str] | frozenset[str]) -> frozenset[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)
