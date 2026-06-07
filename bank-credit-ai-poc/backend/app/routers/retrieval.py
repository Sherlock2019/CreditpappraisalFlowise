from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.services.retrieval_service import retrieve_customer_context

router = APIRouter(tags=["retrieval"])


class RetrievalQueryRequest(BaseModel):
    customer_id: int
    question: str
    top_k: int = Field(default=8, ge=1, le=20)


@router.post("/retrieval/query")
def retrieval_query(payload: RetrievalQueryRequest, db: Session = Depends(get_db)) -> dict:
    if not crud.get_customer(db, payload.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    return retrieve_customer_context(db, payload.customer_id, payload.question, payload.top_k)
