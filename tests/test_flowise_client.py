from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bank-credit-ai-poc" / "backend"))

from app.flowise import client as flowise_client_module
from app.flowise.client import FlowiseClient
from app.flowise.schemas import FlowisePredictionRequest, FlowiseRuntimeVars


def test_flowise_client_falls_back_when_chatflow_id_missing():
    client = FlowiseClient(base_url="http://flowise.local", chatflow_id="")
    result = asyncio.run(client.predict(FlowisePredictionRequest(question="hello")))

    assert result.flowise_used is False
    assert result.fallback_used is True
    assert "FLOWISE_CHATFLOW_ID" in result.error_summary


def test_flowise_client_retries_transient_status(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status_code: int, body: dict):
            self.status_code = status_code
            self._body = body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._body

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            calls.append({"url": url, "json": json, "headers": headers})
            if len(calls) == 1:
                return FakeResponse(503, {})
            return FakeResponse(200, {"text": "credit answer"})

    monkeypatch.setattr(flowise_client_module.httpx, "AsyncClient", FakeAsyncClient)

    client = FlowiseClient(base_url="http://flowise.local", chatflow_id="abc", max_retries=1)
    result = asyncio.run(
        client.predict(
            FlowisePredictionRequest(
                question="summarize",
                vars=FlowiseRuntimeVars(customer_id="1", retrieved_context="context"),
            )
        )
    )

    assert len(calls) == 2
    assert result.flowise_used is True
    assert result.fallback_used is False
    assert result.answer == "credit answer"
    assert calls[0]["json"]["overrideConfig"]["vars"]["customer_id"] == "1"
