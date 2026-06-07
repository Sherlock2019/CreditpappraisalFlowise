import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, SessionLocal, engine
from app.document_cache import document_memory_cache
from app.document_recovery import recover_uploaded_files_from_disk
from app.routers import asset_appraisal, audit, cache, chat, connectors, credit_assessment, customers, documents, flowise, health, loan_policy, retrieval

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bank Credit AI POC",
    description="Credit decision-support assistant with RAG, pgvector, Flowise, and human-review guardrails.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)
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
