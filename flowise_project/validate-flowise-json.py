#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"
EXPECTED_ORDER = [
    "docfactor-all-in-one-flowise-chatflow.json",
    "poc-main-chatflow.json",
    "poc-rag-document-chatflow.json",
    "poc-api-tools-chatflow.json",
    "poc-llm-router-chatflow.json",
    "poc-workspace-export.json",
]
REQUIRED_TOP_LEVEL = {"name", "flowData"}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)secret[_-]?access[_-]?key\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
]
ALLOWED_PLACEHOLDER_MARKERS = ("{{", "}}", "_ENV", "enabled_env", "credentialRef")


def fail(path: Path, message: str) -> tuple[str, bool]:
    return f"❌ {path.name} invalid: {message}", False


def as_flow_data(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("nodes"), list) and isinstance(data.get("edges"), list):
        return data
    flow_data = data.get("flowData")
    if isinstance(flow_data, str):
        return json.loads(flow_data)
    if isinstance(flow_data, dict):
        return flow_data
    raise ValueError("flowData must be a JSON object or JSON string")


def validate_node(path: Path, node: dict[str, Any]) -> str | None:
    for key in ("id", "type", "position", "data", "width", "height", "selected", "dragging"):
        if key not in node:
            return f"node missing {key}: {node}"
    if not isinstance(node["position"], dict) or "x" not in node["position"] or "y" not in node["position"]:
        return f"node position invalid: {node.get('id')}"
    return None


def contains_secret(data: Any) -> str | None:
    text = json.dumps(data, sort_keys=True)
    for pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            snippet = match.group(0)
            if any(marker in snippet for marker in ALLOWED_PLACEHOLDER_MARKERS):
                continue
            return snippet[:80]
    return None


def validate_file(path: Path) -> tuple[str, bool]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return fail(path, f"JSON parse failed: {exc}")

    missing = REQUIRED_TOP_LEVEL - set(data)
    if missing and not (isinstance(data.get("nodes"), list) and isinstance(data.get("edges"), list)):
        return fail(path, f"missing top-level fields: {sorted(missing)}")

    try:
        flow_data = as_flow_data(data)
    except Exception as exc:
        return fail(path, str(exc))

    nodes = flow_data.get("nodes")
    edges = flow_data.get("edges")
    if not isinstance(nodes, list) or not nodes:
        return fail(path, "flowData.nodes must be a non-empty list")
    if not isinstance(edges, list):
        return fail(path, "flowData.edges must be a list")

    node_ids = set()
    for node in nodes:
        if not isinstance(node, dict):
            return fail(path, "node must be an object")
        node_error = validate_node(path, node)
        if node_error:
            return fail(path, node_error)
        node_id = node["id"]
        if node_id in node_ids:
            return fail(path, f"duplicate node id: {node_id}")
        node_ids.add(node_id)

    for edge in edges:
        if not isinstance(edge, dict):
            return fail(path, "edge must be an object")
        for key in ("id", "source", "target", "type"):
            if key not in edge:
                return fail(path, f"edge missing {key}: {edge}")
        if edge["source"] not in node_ids:
            return fail(path, f"edge source not found: {edge['source']}")
        if edge["target"] not in node_ids:
            return fail(path, f"edge target not found: {edge['target']}")

    secret = contains_secret(data)
    if secret:
        return fail(path, f"possible real secret found: {secret}")

    return f"✅ {path.name} valid", True


def main() -> int:
    files_by_name = {path.name: path for path in GENERATED.glob("*.json")}
    files = [files_by_name[name] for name in EXPECTED_ORDER if name in files_by_name]
    files.extend(sorted(path for name, path in files_by_name.items() if name not in EXPECTED_ORDER))
    if not files:
        print("❌ no generated JSON files found")
        return 1

    ok = True
    for path in files:
        line, passed = validate_file(path)
        print(line)
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
