"""The Enterprise Platform lane must be well-formed and must not claim more than the code shows."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

SCRIPT = """
const { withPlatformLane, STAGES } = require('./scripts/lib/platform-canvas');
const base = require('./flowise_project/generated/live-flowise-flowdata-from-db.json');
const once = withPlatformLane(base);
const twice = withPlatformLane(once);
console.log(JSON.stringify({ stages: STAGES, base: { nodes: base.nodes.length, edges: base.edges.length }, once, twiceNodes: twice.nodes.length, twiceEdges: twice.edges.length }));
"""


@pytest.fixture(scope="module")
def canvas():
    result = subprocess.run([NODE, "-e", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    return json.loads(result.stdout)


def test_every_implemented_or_partial_stage_points_at_real_code_and_tests(canvas):
    for stage in canvas["stages"]:
        assert stage["status"] in {"implemented", "partial", "planned"}, stage["key"]
        if stage["status"] == "planned":
            assert not stage["implemented_in"], f"{stage['key']} is planned but claims an implementation"
            continue
        assert stage["implemented_in"], f"{stage['key']} has no implementation path"
        for rel in stage["implemented_in"]:
            assert (ROOT / rel).exists(), f"{stage['key']}: {rel} does not exist"
        for ref in stage["verified_by"]:
            file, _, test_name = ref.partition("::")
            assert (ROOT / file).exists(), f"{stage['key']}: {file} does not exist"
            if test_name:
                assert f"def {test_name}(" in (ROOT / file).read_text(encoding="utf-8"), f"{stage['key']}: missing test {ref}"
        if stage["status"] == "implemented":
            assert stage["verified_by"], f"{stage['key']} is marked Implemented without a test"


def test_lane_is_well_formed_and_idempotent(canvas):
    flow = canvas["once"]
    ids = [n["id"] for n in flow["nodes"]]
    assert len(ids) == len(set(ids))
    nodes = {n["id"]: n for n in flow["nodes"]}

    def handles(anchors):
        # Plain anchors carry an id; selectable outputs (LLM Chain, Prompt Template) list them under options.
        return {a["id"] for a in anchors if "id" in a} | {o["id"] for a in anchors for o in a.get("options", [])}

    for e in flow["edges"]:
        assert e["source"] in nodes and e["target"] in nodes, e["id"]
        assert e["sourceHandle"] in handles(nodes[e["source"]]["data"]["outputAnchors"]), e["id"]
        if e["source"].startswith("platform_") or e["target"].startswith("platform_"):
            assert e["targetHandle"] in handles(nodes[e["target"]]["data"]["inputAnchors"]), e["id"]
    stage_count = len(canvas["stages"])
    assert len(flow["nodes"]) == canvas["base"]["nodes"] + stage_count + 1  # + legend note
    assert len(flow["edges"]) == canvas["base"]["edges"] + stage_count  # chain + link from chat_input
    assert (canvas["twiceNodes"], canvas["twiceEdges"]) == (len(flow["nodes"]), len(flow["edges"]))
    labels = [nodes[f"platform_{s['key']}"]["data"]["label"] for s in canvas["stages"]]
    assert all(label.startswith(("[Implemented] ", "[Partial] ", "[Planned] ")) for label in labels)


def test_stage_code_compiles(canvas):
    for node in canvas["once"]["nodes"]:
        if node["id"].startswith("platform_") and node["data"]["name"] == "customFunction":
            code = node["data"]["inputs"]["javascriptFunction"]
            check = subprocess.run([NODE, "-e", f"new Function('$input', {json.dumps(code)})"], capture_output=True, text=True, timeout=30)
            assert check.returncode == 0, check.stderr
