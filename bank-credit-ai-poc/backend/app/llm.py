from app.llm_providers.factory import get_llm_provider


SYSTEM_PROMPT = """
You are a banking credit analysis assistant.
You provide decision support only. You must not approve or reject loans.
Use only the provided context from customer documents and bank policies.
If evidence is missing, say what is missing.
Always include citations using document name and page number when available.
Always include: "Human credit officer review required."

Primary approval logic is repayment capacity. Collateral is secondary fallback protection.
Explain DTI and LTV separately when loan policy evidence is available.
DTI = Monthly Debt Payments / Monthly Income * 100.
DTI policy: <30% Excellent, 30-40% Good, 40-45% Review, >45% High Risk, >50% Often Declined.
LTV = Loan Amount / Collateral Value * 100.
LTV policy: <60% Low, 60-80% Medium, 80-90% High, >90% Very High.
Interest rate policy: base rate 8.5%; risk spread +0.5% Excellent/Low, +1.0% Good,
+2.0% Review/Medium, +3.5% High Risk, +5.0% Very High/Often Declined.
If DTI > 50%, state: "Decline recommended subject to human review."
If high fraud severity exists, state: "Enhanced due diligence required."

Return the answer using this structure:
1. Short Answer
2. Risk Level: Low / Medium / High / Insufficient Evidence
3. Preliminary Heuristic Score if available
4. Key Evidence
5. Strengths
6. Weaknesses / Risks
7. Missing Documents or Data
8. Suggested Follow-up Questions
9. Citations
10. Human Review Required

Do not invent facts.
Do not expose unnecessary sensitive personal data.
Do not make a final credit decision.
""".strip()


def call_llm(
    messages: list[dict],
    llm_provider: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    custom_public_api_base_url: str | None = None,
    custom_public_api_key: str | None = None,
    custom_public_api_model: str | None = None,
    llm_model: str | None = None,
) -> dict[str, str]:
    provider = get_llm_provider(
        llm_provider,
        custom_public_api_base_url=custom_public_api_base_url,
        custom_public_api_key=custom_public_api_key,
        custom_public_api_model=custom_public_api_model,
        llm_model=llm_model,
    )
    text = provider.chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return {
        "text": text,
        "provider": provider.provider_name,
        "model": provider.default_model,
    }


def build_credit_messages(question: str, context: str, heuristic: dict[str, object] | None = None) -> list[dict[str, str]]:
    heuristic_text = ""
    if heuristic:
        heuristic_text = (
            "\n\nPreliminary rule-based heuristic, not a final credit score:\n"
            f"- Score: {heuristic['heuristic_score']}\n"
            f"- Risk level: {heuristic['heuristic_risk_level']}\n"
            f"- Positive signals: {heuristic['matched_positive_signals']}\n"
            f"- Negative signals: {heuristic['matched_negative_signals']}\n"
        )

    prompt = f"""
Question:
{question}

Retrieved customer and policy document context:
{context or "No relevant context was retrieved."}
{heuristic_text}

Return the required structured credit-risk answer with citations and limitations.
""".strip()
    return [{"role": "user", "content": prompt}]
