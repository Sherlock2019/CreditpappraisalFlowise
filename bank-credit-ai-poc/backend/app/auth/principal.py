from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Principal:
    """Authenticated caller. Built only from a validated token, never from request bodies or prompts."""

    subject: str
    kind: Literal["human", "agent", "anonymous"]
    tenant_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    # Agent runtime identities only: which agent, which run and which customer the token is bound to.
    agent_id: str | None = None
    run_id: str | None = None
    customer_id: int | None = None

    @property
    def is_human(self) -> bool:
        return self.kind == "human"

    @property
    def is_agent(self) -> bool:
        return self.kind == "agent"

    @property
    def actor(self) -> str:
        return f"agent:{self.agent_id}" if self.is_agent else self.subject
