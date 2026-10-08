from __future__ import annotations

import asyncio

import httpx

from app.flowise.schemas import FlowisePredictionRequest, FlowisePredictionResponse

TRANSIENT_STATUS_CODES = {502, 503, 504}
# Postgres vector store node in the flow seeded by scripts/seed-flowise-credit-app.js.
VECTOR_STORE_NODE_ID = "postgres_0"


class FlowiseClient:
    def __init__(
        self,
        base_url: str,
        chatflow_id: str,
        api_key: str | None = None,
        timeout: float = 600,  # local Ollama models can take minutes per answer
        max_retries: int = 2,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.chatflow_id = chatflow_id or ""
        self.api_key = api_key or ""
        self.timeout = timeout
        self.max_retries = max_retries

    async def health(self) -> dict:
        if not self.base_url:
            return {"reachable": False, "error": "Flowise base URL is not configured"}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(self.base_url)
            return {"reachable": response.status_code < 500, "status_code": response.status_code}
        except Exception as exc:
            return {"reachable": False, "error": str(exc)}

    async def predict(self, request: FlowisePredictionRequest) -> FlowisePredictionResponse:
        if not self.base_url:
            return FlowisePredictionResponse(fallback_used=True, error_summary="Flowise base URL is not configured")
        if not self.chatflow_id:
            return FlowisePredictionResponse(fallback_used=True, error_summary="FLOWISE_CHATFLOW_ID is not configured")

        url = f"{self.base_url}/api/v1/prediction/{self.chatflow_id}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        override_config: dict = {"vars": request.vars.model_dump(mode="json")}
        if request.metadata_filter:
            override_config["pgMetadataFilter"] = {VECTOR_STORE_NODE_ID: request.metadata_filter}
        payload = {
            "question": request.question,
            "overrideConfig": override_config,
        }
        last_error: str | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                if response.status_code in TRANSIENT_STATUS_CODES and attempt < self.max_retries:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                response.raise_for_status()
                data = response.json()
                return FlowisePredictionResponse(
                    answer=data.get("text") or data.get("answer") or str(data),
                    raw_response=data,
                    flowise_used=True,
                    fallback_used=False,
                    provider_metadata={"chatflow_id": self.chatflow_id, "base_url": self.base_url},
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(0.25 * (attempt + 1))

        return FlowisePredictionResponse(
            flowise_used=False,
            fallback_used=True,
            error_summary=last_error or "Flowise prediction failed",
            provider_metadata={"chatflow_id": self.chatflow_id, "base_url": self.base_url},
        )
