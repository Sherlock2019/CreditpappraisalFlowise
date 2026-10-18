from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("export_tool_schemas", ROOT / "scripts" / "export_tool_schemas.py")
export_tool_schemas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export_tool_schemas)


def test_committed_tool_schemas_match_the_pydantic_models():
    committed = (ROOT / "flowise_project" / "agentflows" / "tool-schemas.json").read_text(encoding="utf-8")
    assert committed == export_tool_schemas.render(), "Run: .venv/bin/python scripts/export_tool_schemas.py"


def test_every_registered_tool_has_a_route_and_strict_inputs():
    from app.auth.tokens import agent_registry
    from app.main import app

    routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
    registry = agent_registry()
    for name, spec in registry["tools"].items():
        assert (spec["method"], spec["path"]) in routes, name
    schemas = json.loads((ROOT / "flowise_project" / "agentflows" / "tool-schemas.json").read_text(encoding="utf-8"))
    for name in ("evidence.search", "approval.request", "email.draft", "audit.write"):
        assert schemas[name].get("additionalProperties") is False, f"{name} must reject unknown fields"


def test_no_agent_holds_a_human_or_decision_permission():
    from app.auth.policy import HUMAN_ONLY_PERMISSIONS
    from app.auth.tokens import agent_registry

    for agent_id, agent in agent_registry()["agents"].items():
        scopes = set(agent["scopes"])
        assert not scopes & HUMAN_ONLY_PERMISSIONS, agent_id
        assert all(scope.startswith("tool:") for scope in scopes), agent_id
        assert not any("decision" in scope for scope in scopes), agent_id
