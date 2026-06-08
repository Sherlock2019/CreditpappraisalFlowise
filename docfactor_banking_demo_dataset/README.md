# DocFactor Banking Credit Appraisal Demo Dataset

This is a synthetic end-to-end banking dataset for testing:

- Streamlit credit appraisal UI
- FastAPI backend ingestion
- Flowise orchestration
- RAG document retrieval
- pgvector search
- Credit heuristic scoring
- Fraud indicator detection
- Expected answer regression testing

## Contents

- 15 customers
- Good / Medium / High risk borrowers
- Income statements
- 6-month bank statements
- Collateral valuations
- Business financials or personal cashflow files
- Tax return summaries
- Fraud indicators
- Expected assessment outcomes
- RAG test prompts

## Important policy

This dataset is synthetic and for PoC testing only.
The assistant must provide decision support only.
It must not approve or reject loans.
Every answer must include:

Human credit officer review required.

## Suggested Flowise Test Prompt

Summarize this customer's credit risk using uploaded documents. Include citations, missing documents, fraud indicators, and human review warning.

## Recommended Ingestion

1. Load the master workbook:
   DocFactor_Banking_Demo_Master_Dataset.xlsx

2. Ingest each customer folder under:
   customer_documents/

3. Ask the RAG assistant the prompts in:
   RAG_Test_Cases sheet

4. Compare output with:
   Expected_Outcomes sheet
