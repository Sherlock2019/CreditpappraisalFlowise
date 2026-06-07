from fastapi import APIRouter

from app.config import get_settings
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        flowise_configured=bool(settings.flowise_chatflow_id),
        flowise_base_url=settings.flowise_base_url or settings.flowise_api_url,
    )
