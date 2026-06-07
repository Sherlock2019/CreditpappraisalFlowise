#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def normalize_flow_payload(path: Path, deploy: bool) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    flow_data = data.get("flowData")
    if isinstance(flow_data, str):
        flow_data_string = flow_data
    elif isinstance(flow_data, dict):
        flow_data_string = json.dumps(flow_data, separators=(",", ":"))
    else:
        raise ValueError(f"{path} has no usable flowData")

    return {
        "name": data["name"],
        "flowData": flow_data_string,
        "deployed": deploy,
        "isPublic": bool(data.get("isPublic", False)),
        "type": data.get("type", "CHATFLOW"),
        "category": data.get("category", "PoC;AI-Agent-Hub;RAG;Migration")
    }


def post_chatflow(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/chatflows"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def selected_files(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(p for p in GENERATED.glob("*.json") if p.name != "poc-workspace-export.json")
    if args.file:
        return [Path(args.file)]
    raise SystemExit("Use --file path/to/chatflow.json or --all")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import generated PoC chatflows into Flowise.")
    parser.add_argument("--file", help="Path to a generated chatflow JSON file")
    parser.add_argument("--all", action="store_true", help="Import all generated chatflow JSON files")
    parser.add_argument("--deploy", choices=["false", "true"], default="false", help="Set deployed flag on import")
    args = parser.parse_args()

    load_env_file(ROOT / ".env.flowise")
    base_url = os.environ.get("FLOWISE_BASE_URL", "http://localhost:3000")
    api_key = os.environ.get("FLOWISE_API_KEY", "")
    deploy = args.deploy == "true"

    for path in selected_files(args):
        payload = normalize_flow_payload(path, deploy)
        try:
            result = post_chatflow(base_url, api_key, payload)
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            print(f"❌ {path.name}: HTTP {exc.code} {message}")
            return 1
        except Exception as exc:
            print(f"❌ {path.name}: {exc}")
            return 1
        created_id = result.get("id") or result.get("chatflowId") or result.get("data", {}).get("id")
        suffix = f" -> {created_id}" if created_id else ""
        print(f"✅ imported {path.name}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
