from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.audit import log_event
from app.config import get_settings
from app.flowise_client import call_flowise_chat
from app.llm import build_credit_messages, call_llm
from app.llm_providers.factory import normalize_provider, provider_options, resolve_runtime_model
from app.rag import build_context, citations_from_chunks, retrieve_relevant_chunks, retrieve_relevant_chunks_all_customers
from app.database import get_db
from app.workflow_context import build_flowise_workflow_context

router = APIRouter(tags=["chat"])


def _no_llm_fallback_answer(question: str, chunks: list[dict], error: str) -> str:
    if chunks:
        evidence = "\n".join(
            f"- {chunk.get('filename', 'document')} page {chunk.get('page_number') or 'n/a'}: "
            f"{str(chunk.get('chunk_text', '')).strip()[:420]}"
            for chunk in chunks[:5]
        )
        citations = "\n".join(
            f"- {chunk.get('filename', 'document')}, page {chunk.get('page_number') or 'n/a'}"
            for chunk in chunks[:8]
        )
        short_answer = "Relevant document context was retrieved, but the local LLM is not reachable."
    else:
        evidence = "- No relevant document chunks were retrieved. Upload and ingest customer documents first."
        citations = "- No citations available."
        short_answer = "Insufficient evidence. No relevant ingested document context was available."

    return f"""
1. Short Answer
{short_answer}

2. Risk Level: Insufficient Evidence

3. Preliminary Heuristic Score if available
Not available from this chat fallback.

4. Key Evidence
{evidence}

5. Strengths
Cannot be reliably assessed without the local LLM and sufficient ingested evidence.

6. Weaknesses / Risks
Local model response failed: {error}

7. Missing Documents or Data
Confirm the customer documents are uploaded and ingested. Confirm Ollama is running and serving the selected local model.

8. Suggested Follow-up Questions
- Which documents have been uploaded and ingested?
- Are recent financial statements, repayment history, and bank policy documents available?
- Is Ollama running on port 11434 with the configured model?

9. Citations
{citations}

10. Human Review Required
Human credit officer review required.
""".strip()


@router.post("/chat", response_model=schemas.ChatResponse)
async def chat(payload: schemas.ChatRequest, db: Session = Depends(get_db)) -> schemas.ChatResponse:
    all_customers = payload.customer_id is None or payload.customer_id <= 0
    customer = None if all_customers else crud.get_customer(db, payload.customer_id)
    if not all_customers and not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    provider = normalize_provider(payload.llm_provider)
    runtime_model = resolve_runtime_model(provider, payload.llm_model or payload.custom_public_api_model)
    log_event(
        db,
        "chat_question",
        None if all_customers else payload.customer_id,
        {
            "provider": provider,
            "model": runtime_model or "",
            "question_length": len(payload.message),
            "session_id": payload.session_id,
            "scope": "all_customers" if all_customers else "selected_customer",
        },
    )

    session_id = payload.session_id
    if all_customers:
        session_id = 0
    elif session_id is None:
        session = models.ChatSession(customer_id=payload.customer_id)
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

    chunks = retrieve_relevant_chunks_all_customers(db, payload.message) if all_customers else retrieve_relevant_chunks(db, payload.customer_id, payload.message)
    context = build_context(chunks)
    citations = citations_from_chunks(chunks)
    chunk_ids = [chunk.get("chunk_index") for chunk in chunks]
    workflow_context = {} if all_customers else build_flowise_workflow_context(db, payload.customer_id, payload.workflow_context)

    if not all_customers:
        db.add(models.ChatMessage(session_id=session_id, customer_id=payload.customer_id, role="user", content=payload.message))
        db.commit()

    settings = get_settings()
    flowise_used = False
    fallback_used = False
    try:
        if provider == "custom_public_api":
            result = call_llm(
                build_credit_messages(payload.message, context),
                llm_provider=provider,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                custom_public_api_base_url=payload.custom_public_api_base_url,
                custom_public_api_key=payload.custom_public_api_key,
                custom_public_api_model=payload.custom_public_api_model,
                llm_model=runtime_model,
            )
            fallback_used = True
        elif settings.flowise_chatflow_id and not all_customers:
            result = await call_flowise_chat(
                payload.message,
                payload.customer_id,
                context,
                llm_provider=provider,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                custom_public_api_model=runtime_model,
                llm_model=runtime_model,
                workflow_context=workflow_context,
            )
            flowise_used = True
        else:
            result = call_llm(
                build_credit_messages(payload.message, context),
                llm_provider=provider,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                llm_model=runtime_model,
            )
    except Exception as exc:
        event_type = "flowise_error" if settings.flowise_chatflow_id and provider != "custom_public_api" and not all_customers else "llm_error"
        log_event(db, event_type, None if all_customers else payload.customer_id, {"error": str(exc), "provider": provider, "model": runtime_model or "", "scope": "all_customers" if all_customers else "selected_customer"})
        if settings.flowise_chatflow_id and provider != "custom_public_api" and not all_customers:
            try:
                result = call_llm(
                    build_credit_messages(payload.message, context),
                    llm_provider=provider,
                    temperature=payload.temperature,
                    max_tokens=payload.max_tokens,
                    llm_model=runtime_model,
                )
                fallback_used = True
            except Exception as fallback_exc:
                log_event(db, "llm_error", payload.customer_id, {"error": str(fallback_exc), "provider": provider})
                result = {
                    "text": _no_llm_fallback_answer(payload.message, chunks, str(fallback_exc)),
                    "provider": "local_rule_based_fallback",
                    "model": "llm_unavailable",
                }
                fallback_used = True
        elif all_customers:
            result = {
                "text": _no_llm_fallback_answer(payload.message, chunks, str(exc)),
                "provider": "local_rule_based_fallback",
                "model": "llm_unavailable",
            }
            fallback_used = True
        else:
            raise HTTPException(status_code=500, detail=f"AI response failed: {exc}") from exc

    answer = result["text"]
    if "Human credit officer review required" not in answer:
        answer = f"{answer}\n\nHuman credit officer review required."

    if not all_customers:
        db.add(
            models.ChatMessage(
                session_id=session_id,
                customer_id=payload.customer_id,
                role="assistant",
                content=answer,
            )
        )
        db.commit()
    log_event(
        db,
        "chat_response",
        None if all_customers else payload.customer_id,
        {
            "provider": result["provider"],
            "model": result["model"],
            "retrieved_chunk_ids": chunk_ids,
            "flowise_used": flowise_used,
            "fallback_used": fallback_used,
            "scope": "all_customers" if all_customers else "selected_customer",
        },
    )
    return schemas.ChatResponse(
        session_id=session_id,
        answer=answer,
        citations=citations,
        retrieved_chunks=chunks,
        llm_provider_used=result["provider"],
        llm_model_used=result["model"],
        flowise_used=flowise_used,
        fallback_used=fallback_used,
    )


@router.get("/retrieval/{customer_id}", response_model=list[schemas.RetrievedChunk])
def retrieval(customer_id: int, question: str, top_k: int = 8, db: Session = Depends(get_db)) -> list[schemas.RetrievedChunk]:
    if not crud.get_customer(db, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    return retrieve_relevant_chunks(db, customer_id, question, top_k=top_k)


@router.get("/llm/provider-options", response_model=list[schemas.ProviderOption])
def llm_provider_options() -> list[schemas.ProviderOption]:
    return provider_options()
