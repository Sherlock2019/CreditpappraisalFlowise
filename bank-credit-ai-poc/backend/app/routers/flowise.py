from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.flowise.client import FlowiseClient
from app.flowise.schemas import FlowisePredictionRequest, FlowisePredictionResponse

router = APIRouter(tags=["flowise"])


def _client() -> FlowiseClient:
    settings = get_settings()
    return FlowiseClient(
        base_url=settings.flowise_base_url or settings.flowise_api_url,
        api_key=settings.flowise_api_key,
        chatflow_id=settings.flowise_chatflow_id,
    )


@router.get("/flowise/health")
async def flowise_health() -> dict:
    settings = get_settings()
    health = await _client().health()
    return {
        **health,
        "configured": bool(settings.flowise_chatflow_id),
        "chatflow_id": settings.flowise_chatflow_id,
        "base_url": settings.flowise_base_url or settings.flowise_api_url,
    }


@router.post("/flowise/predict", response_model=FlowisePredictionResponse)
async def flowise_predict(payload: FlowisePredictionRequest) -> FlowisePredictionResponse:
    return await _client().predict(payload)
