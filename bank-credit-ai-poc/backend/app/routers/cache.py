from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.document_cache import document_memory_cache

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/status")
def cache_status() -> dict[str, int]:
    return document_memory_cache.summary()


@router.post("/reload")
def reload_cache(db: Session = Depends(get_db)) -> dict[str, int]:
    return document_memory_cache.warm_from_db(db)
