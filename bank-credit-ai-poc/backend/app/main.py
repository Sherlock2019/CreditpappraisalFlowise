import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.correlation import CorrelationIdMiddleware
from app.database import Base, SessionLocal, engine
from app.document_cache import document_memory_cache
from app.document_recovery import recover_uploaded_files_from_disk
from app.errors import register_error_handlers
from app.routers import asset_appraisal, audit, cache, chat, connectors, credit_assessment, customers, documents, flowise, health, loan_policy, retrieval
from app.routers.v1 import agents as v1_agents
from app.routers.v1 import approvals as v1_approvals
from app.routers.v1 import audit as v1_audit
from app.routers.v1 import tools as v1_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Bank Credit AI POC",
    description=(
        "Credit decision-support assistant with RAG, pgvector, Flowise, and human-review guardrails.\n\n"
        "`/api/v1` requires a bearer token: an OIDC token for people, or a run-bound agent token minted by "
        "FastAPI for Flowise agents. Unversioned routes are the legacy LISA/Streamlit API."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)

app.include_router(health.router)
app.include_router(cache.router)
app.include_router(audit.router)
app.include_router(customers.router)
app.include_router(documents.router)
app.include_router(connectors.router)
app.include_router(retrieval.router)
app.include_router(flowise.router)
app.include_router(chat.router)
app.include_router(credit_assessment.router)
app.include_router(loan_policy.router)
app.include_router(asset_appraisal.router)
app.include_router(v1_agents.router)
app.include_router(v1_approvals.router)
app.include_router(v1_audit.router)
app.include_router(v1_tools.router)


def _ensure_tenant_column() -> None:
    # create_all() does not add columns to existing tables. Alembic replaces this (IMPLEMENTATION_PLAN M1).
    if engine.dialect.name != "postgresql":
        return
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", settings.default_tenant_id):
        raise RuntimeError("DEFAULT_TENANT_ID must be 1-64 characters of letters, digits, '_' or '-'")
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE customers ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT '{settings.default_tenant_id}'"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_tenant_id ON customers(tenant_id)"))


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_tenant_column()
    db = SessionLocal()
    try:
        recovery_summary = recover_uploaded_files_from_disk(db)
        logger.info("Uploaded document disk recovery complete: %s", recovery_summary)
        cache_summary = document_memory_cache.warm_from_db(db)
        logger.info("Document memory cache warmed: %s", cache_summary)
    except Exception as exc:
        logger.warning("Document memory cache warm-up skipped: %s", exc)
    finally:
        db.close()
    logger.info("Bank Credit AI POC backend started. Swagger is available at /docs")
