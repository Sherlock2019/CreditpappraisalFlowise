"""Runs the Agentflow generator check and validator so CI fails when the flows and the gateway drift apart."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def test_generated_agentflows_pass_wiring_security_and_dry_run_checks():
    result = subprocess.run([NODE, "flowise_project/agentflows/validate-agentflows.js"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ERR" not in result.stdout
    assert result.stdout.count("  ok  ") >= 27


def test_generated_agentflows_are_up_to_date_with_the_generator(tmp_path):
    components = ROOT / ".tools" / "flowise-3.1.2" / "node_modules" / "flowise-components"
    if not components.exists():
        pytest.skip("flowise-components is not installed under .tools")
    generated = ROOT / "flowise_project" / "agentflows" / "generated"
    before = {p.name: p.read_text(encoding="utf-8") for p in generated.glob("*.json")}
    try:
        subprocess.run([NODE, "flowise_project/agentflows/build-agentflows.js"], cwd=ROOT, check=True, capture_output=True, timeout=120)
        after = {p.name: p.read_text(encoding="utf-8") for p in generated.glob("*.json")}
    finally:
        for name, text in before.items():
            (generated / name).write_text(text, encoding="utf-8")
    # local-dev is rewritten by seed-flowise-agentflow.js with whichever Ollama model is installed.
    stale = [name for name in before if "local-dev" not in name and before[name] != after.get(name)]
    assert not stale, f"Regenerate with node flowise_project/agentflows/build-agentflows.js: {stale}"
