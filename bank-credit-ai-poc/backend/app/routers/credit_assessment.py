from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.audit import log_event
from app.credit_scoring import calculate_heuristic_score
from app.database import get_db
from app.llm import build_credit_messages, call_llm
from app.config import get_settings
from app.flowise_client import call_flowise_chat
from app.llm_providers.factory import normalize_provider, resolve_runtime_model
from app.rag import build_context, citations_from_chunks, retrieve_relevant_chunks
from app.workflow_context import build_flowise_workflow_context

router = APIRouter(prefix="/credit-assessment", tags=["credit assessment"])

ASSESSMENT_PROMPT = (
    "Analyze the uploaded customer credit documents and provide a credit risk assessment. "
    "Do not approve or reject the loan. Provide risk level, strengths, weaknesses, missing documents, "
    "confidence level, limitations, and citations. Human credit officer review required."
)


@router.post("/{customer_id}", response_model=schemas.CreditAssessmentResponse)
async def generate_credit_assessment(
    customer_id: int,
    payload: schemas.CreditAssessmentRequest | None = None,
    db: Session = Depends(get_db),
) -> schemas.CreditAssessmentResponse:
    payload = payload or schemas.CreditAssessmentRequest()
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    provider = normalize_provider(payload.llm_provider)
    runtime_model = resolve_runtime_model(provider, payload.llm_model or payload.custom_public_api_model)
    chunks = retrieve_relevant_chunks(db, customer_id, ASSESSMENT_PROMPT, top_k=12)
    context = build_context(chunks)
    heuristic = calculate_heuristic_score(context)
    citations = citations_from_chunks(chunks)
    settings = get_settings()
    flowise_used = False
    fallback_used = False
    workflow_context = build_flowise_workflow_context(db, customer_id, payload.workflow_context)

    try:
        if provider == "custom_public_api":
            result = call_llm(
                build_credit_messages(ASSESSMENT_PROMPT, context, heuristic),
                llm_provider=provider,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                custom_public_api_base_url=payload.custom_public_api_base_url,
                custom_public_api_key=payload.custom_public_api_key,
                custom_public_api_model=payload.custom_public_api_model,
                llm_model=runtime_model,
            )
            fallback_used = True
        elif settings.flowise_chatflow_id:
            result = await call_flowise_chat(
                ASSESSMENT_PROMPT,
                customer_id,
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
                build_credit_messages(ASSESSMENT_PROMPT, context, heuristic),
                llm_provider=provider,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                llm_model=runtime_model,
            )
    except Exception as exc:
        event_type = "flowise_error" if settings.flowise_chatflow_id and provider != "custom_public_api" else "llm_error"
        log_event(db, event_type, customer_id, {"error": str(exc), "provider": provider, "model": runtime_model or ""})
        if settings.flowise_chatflow_id and provider != "custom_public_api":
            try:
                result = call_llm(
                    build_credit_messages(ASSESSMENT_PROMPT, context, heuristic),
                    llm_provider=provider,
                    temperature=payload.temperature,
                    max_tokens=payload.max_tokens,
                    llm_model=runtime_model,
                )
                fallback_used = True
            except Exception as fallback_exc:
                log_event(db, "llm_error", customer_id, {"error": str(fallback_exc), "provider": provider})
                raise HTTPException(status_code=500, detail=f"Credit assessment failed: {fallback_exc}") from fallback_exc
        else:
            raise HTTPException(status_code=500, detail=f"Credit assessment failed: {exc}") from exc

    answer = result["text"]
    if "Human credit officer review required" not in answer:
        answer = f"{answer}\n\nHuman credit officer review required."

    assessment = models.CreditAssessment(
        customer_id=customer_id,
        risk_level=str(heuristic["heuristic_risk_level"]),
        score=int(heuristic["heuristic_score"]),
        summary=answer,
        strengths=", ".join(heuristic["matched_positive_signals"]),
        weaknesses=", ".join(heuristic["matched_negative_signals"]),
        missing_documents="See AI response for missing documents or data.",
        human_review_required=True,
    )
    db.add(assessment)
    db.commit()
    log_event(
        db,
        "credit_assessment_generated",
        customer_id,
        {
            "assessment_id": assessment.id,
            "provider": result["provider"],
            "model": result["model"],
            "flowise_used": flowise_used,
            "fallback_used": fallback_used,
        },
    )

    return schemas.CreditAssessmentResponse(
        customer_id=customer_id,
        answer=answer,
        heuristic_score=int(heuristic["heuristic_score"]),
        heuristic_risk_level=str(heuristic["heuristic_risk_level"]),
        matched_positive_signals=list(heuristic["matched_positive_signals"]),
        matched_negative_signals=list(heuristic["matched_negative_signals"]),
        citations=citations,
        retrieved_chunks=chunks,
        llm_provider_used=result["provider"],
        llm_model_used=result["model"],
        flowise_used=flowise_used,
        fallback_used=fallback_used,
    )
