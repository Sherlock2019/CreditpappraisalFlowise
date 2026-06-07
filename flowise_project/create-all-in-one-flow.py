#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
GENERATED = ROOT / "generated"
GENERATED.mkdir(exist_ok=True)

CHATFLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820"
CHATFLOW_NAME = "Docfactor Full Banking Workflow"
LIVE_FLOW_PATH = REPO / "bank-credit-ai-poc" / "flowise" / "flows" / "docfactor_credit_appraisal_rag_backend.json"
LIVE_DB_PATH = REPO / "bank-credit-ai-poc" / "flowise" / ".flowise" / "database.sqlite"

CANONICAL_OUT = GENERATED / "docfactor-all-in-one-flowise-chatflow.json"
ALIAS_OUTS = [
    GENERATED / "best-docfactor-all-in-one-flowise-chatflow.json",
    GENERATED / "docfactor-best-all-in-one-flowise-chatflow-ui-import.json",
    GENERATED / "docfactor-best-all-in-one-flowise-chatflow-api-import.json",
    ROOT / "docfactor-best-all-in-one-flowise-chatflow-ui-import.json",
    ROOT / "docfactor-best-all-in-one-flowise-chatflow-api-import.json",
]
FLOWDATA_OUTS = [GENERATED / "docfactor-best-flowdata-only.json", ROOT / "docfactor-best-flowdata-only.json"]

BACKEND_BASE_URL = "http://host.docker.internal:8000"

RUNTIME_VARIABLES = [
    "customer_id",
    "question",
    "llm_provider",
    "llm_model",
    "temperature",
    "max_tokens",
    "loan_amount",
    "collateral_value",
    "monthly_income",
    "monthly_debt_payments",
    "term_months",
    "retrieved_context",
    "citations",
    "workflow_state_json",
]

DATABASE_TABLES = [
    "customers",
    "documents",
    "document_chunks",
    "chat_sessions",
    "chat_messages",
    "credit_assessments",
    "loan_policy_scores",
    "approval_committee_cases",
    "final_decisions",
    "decision_email_drafts",
    "audit_logs",
]

BACKEND_ENDPOINTS = [
    {"node": "Document Upload", "endpoint": "POST /documents/upload"},
    {"node": "Document Ingest", "endpoint": "POST /ingest/{document_id}"},
    {"node": "HTTP Retrieval Tool", "endpoint": "POST /retrieval/query"},
    {"node": "Credit Assessment", "endpoint": "POST /credit-assessment/{customer_id}"},
    {"node": "Loan Policy Scoring", "endpoint": "POST /loan-policy/score"},
    {"node": "Approval Committee", "endpoint": "POST /approval-committee/submit"},
    {"node": "Final Decision", "endpoint": "POST /final-decision"},
    {"node": "Customer Email Draft", "endpoint": "POST /customer-decision-email/draft"},
    {"node": "Audit Logging", "endpoint": "POST /audit"},
]

PROMPT = """
You are LISA, a banking credit analysis assistant inside HyperSpeed Banking AI Copilot.

You provide decision support only. You must not approve or reject loans.
Use only the retrieved customer document context, bank policy context, and supplied workflow state.
If evidence is missing, say what is missing.
Always include citations using document name and page number when available.
Always include: "Human credit officer review required."

Runtime packet from FastAPI:
{question}

Return:
1. Short Answer
2. Risk Level
3. Preliminary Heuristic Score if available
4. Key Evidence
5. Strengths
6. Weaknesses / Risks
7. Missing Documents or Data
8. Loan Policy Scoring
9. Approval Committee / Final Decision Status
10. Suggested Follow-up Questions
11. Citations
12. Human Review Required
""".strip()


def _input_anchor(node_id: str) -> dict[str, Any]:
    return {
        "label": "Input",
        "name": "input",
        "type": "string | number | boolean | json | array",
        "optional": True,
        "id": f"{node_id}-input-input-string|number|boolean|json|array",
    }


def _output_anchor(node_id: str) -> dict[str, Any]:
    return {
        "id": f"{node_id}-output-output-string|number|boolean|json|array",
        "name": "output",
        "label": "Output",
        "type": "string | number | boolean | json | array",
    }


def custom_function_node(
    node_id: str,
    label: str,
    x: int,
    y: int,
    *,
    code: str,
    input_variables: dict[str, Any] | None = None,
    width: int = 320,
    height: int = 300,
) -> dict[str, Any]:
    return {
        "width": width,
        "height": height,
        "id": node_id,
        "position": {"x": x, "y": y},
        "type": "customNode",
        "data": {
            "id": node_id,
            "label": label,
            "version": 3,
            "name": "customFunction",
            "type": "CustomFunction",
            "baseClasses": ["CustomFunction", "Utilities"],
            "category": "Utilities",
            "description": label,
            "inputParams": [
                {
                    "label": "Input Variables",
                    "name": "functionInputVariables",
                    "type": "json",
                    "optional": True,
                    "acceptVariable": True,
                    "list": True,
                    "id": f"{node_id}-input-functionInputVariables-json",
                },
                {
                    "label": "Function Name",
                    "name": "functionName",
                    "type": "string",
                    "optional": True,
                    "id": f"{node_id}-input-functionName-string",
                },
                {
                    "label": "Javascript Function",
                    "name": "javascriptFunction",
                    "type": "code",
                    "id": f"{node_id}-input-javascriptFunction-code",
                },
            ],
            "inputAnchors": [_input_anchor(node_id)],
            "inputs": {
                "functionInputVariables": json.dumps(input_variables or {}, separators=(",", ":")),
                "functionName": label.replace(" ", "_").lower(),
                "javascriptFunction": code,
            },
            "outputAnchors": [_output_anchor(node_id)],
            "outputs": {"output": "output"},
            "selected": False,
        },
        "selected": False,
        "positionAbsolute": {"x": x, "y": y},
        "dragging": False,
    }


def http_function_code(path: str, method: str = "POST") -> str:
    payload = "$input"
    if method == "GET":
        return f"""
const baseUrl = "{BACKEND_BASE_URL}";
return {{
  component: "{path}",
  method: "GET",
  endpoint: baseUrl + "{path}",
  input: {payload}
}};
""".strip()
    return f"""
const baseUrl = "{BACKEND_BASE_URL}";
return {{
  component: "{path}",
  method: "{method}",
  endpoint: baseUrl + "{path}",
  input: {payload}
}};
""".strip()


def passthrough_code(component: str) -> str:
    return f"""
return {{
  component: "{component}",
  input: $input
}};
""".strip()


def node_chat_ollama(node_id: str, label: str, model: str, x: int, y: int) -> dict[str, Any]:
    return {
        "width": 300,
        "height": 560,
        "id": node_id,
        "position": {"x": x, "y": y},
        "type": "customNode",
        "data": {
            "id": node_id,
            "label": label,
            "version": 5,
            "name": "chatOllama",
            "type": "ChatOllama",
            "baseClasses": ["ChatOllama", "BaseChatModel", "BaseLanguageModel", "Runnable"],
            "category": "Chat Models",
            "description": label,
            "inputParams": [
                {"label": "Base URL", "name": "baseUrl", "type": "string", "id": f"{node_id}-input-baseUrl-string"},
                {"label": "Model Name", "name": "modelName", "type": "string", "id": f"{node_id}-input-modelName-string"},
                {"label": "Temperature", "name": "temperature", "type": "number", "optional": True, "id": f"{node_id}-input-temperature-number"},
            ],
            "inputAnchors": [],
            "inputs": {"baseUrl": "http://127.0.0.1:11434", "modelName": model, "temperature": "0.2"},
            "outputAnchors": [
                {
                    "id": f"{node_id}-output-chatOllama-ChatOllama|BaseChatModel|BaseLanguageModel|Runnable",
                    "name": "chatOllama",
                    "label": label,
                    "type": "ChatOllama | BaseChatModel | BaseLanguageModel | Runnable",
                }
            ],
            "outputs": {},
            "selected": False,
        },
        "selected": False,
        "positionAbsolute": {"x": x, "y": y},
        "dragging": False,
    }


def node_prompt_template(
    node_id: str = "prompt_template",
    label: str = "Prompt Template",
    x: int = 1180,
    y: int = 260,
    template: str = PROMPT,
) -> dict[str, Any]:
    return {
        "width": 430,
        "height": 520,
        "id": node_id,
        "position": {"x": x, "y": y},
        "type": "customNode",
        "data": {
            "id": node_id,
            "label": label,
            "version": 1,
            "name": "promptTemplate",
            "type": "PromptTemplate",
            "baseClasses": ["PromptTemplate", "BaseStringPromptTemplate", "BasePromptTemplate"],
            "category": "Prompts",
            "description": "Credit appraisal prompt with RAG context and citations",
            "inputParams": [
                {"label": "Template", "name": "template", "type": "string", "rows": 4, "id": f"{node_id}-input-template-string"},
                {"label": "Format Prompt Values", "name": "promptValues", "type": "json", "optional": True, "acceptVariable": True, "list": True, "id": f"{node_id}-input-promptValues-json"},
            ],
            "inputAnchors": [_input_anchor(node_id)],
            "inputs": {"template": template, "promptValues": "{}"},
            "outputAnchors": [
                {
                    "id": f"{node_id}-output-promptTemplate-PromptTemplate|BaseStringPromptTemplate|BasePromptTemplate",
                    "name": "promptTemplate",
                    "label": "PromptTemplate",
                    "type": "PromptTemplate | BaseStringPromptTemplate | BasePromptTemplate",
                }
            ],
            "outputs": {},
            "selected": False,
        },
        "selected": False,
        "positionAbsolute": {"x": x, "y": y},
        "dragging": False,
    }


def node_llm_chain(node_id: str = "llm_chain", label: str = "LLM Chain", x: int = 1960, y: int = 260) -> dict[str, Any]:
    return {
        "width": 330,
        "height": 450,
        "id": node_id,
        "position": {"x": x, "y": y},
        "type": "customNode",
        "data": {
            "id": node_id,
            "label": label,
            "version": 3,
            "name": "llmChain",
            "type": "LLMChain",
            "baseClasses": ["LLMChain", "BaseChain", "Runnable"],
            "category": "Chains",
            "description": "Credit assessment chain",
            "inputParams": [
                {"label": "Chain Name", "name": "chainName", "type": "string", "optional": True, "id": f"{node_id}-input-chainName-string"}
            ],
            "inputAnchors": [
                {"label": "Language Model", "name": "model", "type": "BaseLanguageModel", "id": f"{node_id}-input-model-BaseLanguageModel"},
                {"label": "Prompt", "name": "prompt", "type": "BasePromptTemplate", "id": f"{node_id}-input-prompt-BasePromptTemplate"},
                {"label": "Output Parser", "name": "outputParser", "type": "BaseLLMOutputParser", "optional": True, "id": f"{node_id}-input-outputParser-BaseLLMOutputParser"},
            ],
            "inputs": {
                "model": "{{ollama_gemma.data.instance}}",
                "prompt": "{{prompt_template.data.instance}}",
                "outputParser": "",
                "chainName": CHATFLOW_NAME,
            },
            "outputAnchors": [
                {
                    "name": "output",
                    "label": "Output",
                    "type": "options",
                    "options": [
                        {
                            "id": f"{node_id}-output-llmChain-LLMChain|BaseChain|Runnable",
                            "name": "llmChain",
                            "label": "LLM Chain",
                            "type": "LLMChain | BaseChain | Runnable",
                        },
                        {
                            "id": f"{node_id}-output-outputPrediction-string|json",
                            "name": "outputPrediction",
                            "label": "Output Prediction",
                            "type": "string | json",
                        },
                    ],
                    "default": "llmChain",
                }
            ],
            "outputs": {"output": "llmChain"},
            "selected": False,
        },
        "selected": False,
        "positionAbsolute": {"x": x, "y": y},
        "dragging": False,
    }


def edge(source: str, target: str, source_handle: str | None = None, target_handle: str | None = None) -> dict[str, Any]:
    source_handle = source_handle or f"{source}-output-output-string|number|boolean|json|array"
    target_handle = target_handle or f"{target}-input-input-string|number|boolean|json|array"
    return {
        "source": source,
        "sourceHandle": source_handle,
        "target": target,
        "targetHandle": target_handle,
        "type": "buttonedge",
        "id": f"{source}-{source_handle}-{target}-{target_handle}",
    }


def build_flow_data() -> dict[str, Any]:
    nodes = [
        custom_function_node("chat_input", "Chat Input", -420, 260, code=passthrough_code("Chat Input")),
        custom_function_node("runtime_vars", "Runtime Variables", -40, 260, code=passthrough_code("Runtime Variables")),
        custom_function_node("http_retrieval_tool", "HTTP Retrieval Tool", 340, 260, code=http_function_code("/retrieval/query")),
        custom_function_node("document_upload", "Document Upload", 340, 760, code=http_function_code("/documents/upload")),
        custom_function_node("parser", "Parser", 720, 760, code=passthrough_code("Parser: app/document_parser.py")),
        custom_function_node("chunker", "Chunker", 1100, 760, code=passthrough_code("Chunker: app/document_parser.py")),
        custom_function_node("embeddings", "Embeddings", 1480, 760, code=passthrough_code("Embeddings: app/embeddings.py")),
        custom_function_node("postgresql", "PostgreSQL", 1860, 760, code=passthrough_code("PostgreSQL: customers/documents/document_chunks")),
        custom_function_node("pgvector", "pgvector", 2240, 760, code=passthrough_code("pgvector: document_chunks.embedding vector index")),
        custom_function_node("retriever", "Retriever", 720, 260, code=passthrough_code("Retriever: app/rag.py")),
        custom_function_node("citation_builder", "Citation Builder", 960, 260, code=passthrough_code("Citation Builder: citations_from_chunks")),
        node_prompt_template(),
        custom_function_node("llm_router", "LLM Router", 1640, 260, code=passthrough_code("LLM Router")),
        custom_function_node("ollama_mistral", "Ollama: Mistral", 1500, -330, code=passthrough_code("Ollama Mistral provider option")),
        node_chat_ollama("ollama_gemma", "Ollama: Gemma", "gemma2:9b", 1840, -360),
        custom_function_node("openai_provider", "OpenAI", 2180, -330, code=passthrough_code("OpenAI provider")),
        custom_function_node("deepseek_provider", "DeepSeek", 2560, -330, code=passthrough_code("DeepSeek provider")),
        custom_function_node("custom_provider", "Custom API", 2940, -330, code=passthrough_code("Custom OpenAI-compatible provider")),
        node_llm_chain(),
        custom_function_node("credit_assessment", "Credit Assessment", 2340, 260, code=http_function_code("/credit-assessment/{customer_id}")),
        custom_function_node("output_parser", "Output Parser", 2720, 260, code=passthrough_code("Structured output parser")),
        custom_function_node("loan_policy_scoring", "Loan Policy Scoring", 3100, 260, code=http_function_code("/loan-policy/score")),
        custom_function_node("dti", "DTI", 3100, 700, code=passthrough_code("DTI = monthly debt payments / monthly income")),
        custom_function_node("ltv", "LTV", 3480, 700, code=passthrough_code("LTV = loan amount / collateral value")),
        custom_function_node("interest_rate", "Interest Rate", 3860, 700, code=passthrough_code("Estimated interest rate")),
        custom_function_node("monthly_payment", "Monthly Payment", 4240, 700, code=passthrough_code("Estimated monthly payment")),
        custom_function_node("recommendation", "Recommendation", 4620, 700, code=passthrough_code("Policy recommendation")),
        custom_function_node("approval_committee", "Approval Committee", 3480, 260, code=http_function_code("/approval-committee/submit")),
        custom_function_node("final_decision", "Final Decision", 3860, 260, code=http_function_code("/final-decision")),
        custom_function_node("customer_email_draft", "Customer Email Draft", 4240, 260, code=http_function_code("/customer-decision-email/draft")),
        custom_function_node("audit_logging", "Audit Logging", 4620, 260, code=http_function_code("/audit")),
        custom_function_node("chat_output", "Chat Output", 5000, 260, code=passthrough_code("Chat Output / UI Response")),
    ]

    edges = [
        edge("chat_input", "runtime_vars"),
        edge("runtime_vars", "http_retrieval_tool"),
        edge("http_retrieval_tool", "retriever"),
        edge("document_upload", "parser"),
        edge("parser", "chunker"),
        edge("chunker", "embeddings"),
        edge("embeddings", "postgresql"),
        edge("postgresql", "pgvector"),
        edge("pgvector", "retriever"),
        edge("retriever", "citation_builder"),
        edge("citation_builder", "credit_assessment"),
        edge("credit_assessment", "output_parser"),
        edge("output_parser", "loan_policy_scoring"),
        edge("loan_policy_scoring", "dti"),
        edge("loan_policy_scoring", "ltv"),
        edge("loan_policy_scoring", "interest_rate"),
        edge("loan_policy_scoring", "monthly_payment"),
        edge("loan_policy_scoring", "recommendation"),
        edge("dti", "recommendation"),
        edge("ltv", "recommendation"),
        edge("interest_rate", "monthly_payment"),
        edge("monthly_payment", "recommendation"),
        edge("recommendation", "approval_committee"),
        edge("approval_committee", "final_decision"),
        edge("final_decision", "customer_email_draft"),
        edge("customer_email_draft", "audit_logging"),
        edge("audit_logging", "chat_output"),
        edge("chat_output", "prompt_template", target_handle="prompt_template-input-input-string|number|boolean|json|array"),
        edge("citation_builder", "llm_router"),
        edge("llm_router", "ollama_mistral"),
        edge("ollama_mistral", "openai_provider"),
        edge("openai_provider", "deepseek_provider"),
        edge("deepseek_provider", "custom_provider"),
        edge("custom_provider", "prompt_template", target_handle="prompt_template-input-input-string|number|boolean|json|array"),
        edge(
            "prompt_template",
            "llm_chain",
            "prompt_template-output-promptTemplate-PromptTemplate|BaseStringPromptTemplate|BasePromptTemplate",
            "llm_chain-input-prompt-BasePromptTemplate",
        ),
        edge(
            "ollama_gemma",
            "llm_chain",
            "ollama_gemma-output-chatOllama-ChatOllama|BaseChatModel|BaseLanguageModel|Runnable",
            "llm_chain-input-model-BaseLanguageModel",
        ),
    ]
    return {"nodes": nodes, "edges": edges, "viewport": {"x": 20, "y": 50, "zoom": 0.45}}


def build_chatflow(flow_data: dict[str, Any], *, stringify_flow_data: bool = False) -> dict[str, Any]:
    return {
        "id": CHATFLOW_ID,
        "name": CHATFLOW_NAME,
        "description": "Rebuilt from scratch: connected Flowise canvas containing parser, chunker, embeddings, PostgreSQL, pgvector, retriever, citations, LLM, policy, committee, decision, email, and audit components.",
        "deployed": True,
        "isPublic": True,
        "type": "CHATFLOW",
        "category": "Production;Retail-Banking;Credit-Appraisal;RAG;Policy-Workflow",
        "runtimeVariables": RUNTIME_VARIABLES,
        "backendEndpoints": BACKEND_ENDPOINTS,
        "databaseTables": DATABASE_TABLES,
        "flowData": json.dumps(flow_data, separators=(",", ":")) if stringify_flow_data else flow_data,
    }


def validate_flow_data(flow_data: dict[str, Any]) -> dict[str, Any]:
    node_ids = [node["id"] for node in flow_data["nodes"]]
    duplicate_nodes = sorted({node_id for node_id in node_ids if node_ids.count(node_id) > 1})
    missing = [edge for edge in flow_data["edges"] if edge["source"] not in node_ids or edge["target"] not in node_ids]
    if duplicate_nodes or missing:
        raise RuntimeError(json.dumps({"duplicate_nodes": duplicate_nodes, "missing_edge_nodes": missing}, indent=2))
    return {"node_count": len(flow_data["nodes"]), "edge_count": len(flow_data["edges"])}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_outputs(flow_data: dict[str, Any]) -> list[Path]:
    canonical = build_chatflow(flow_data)
    api_import = build_chatflow(flow_data, stringify_flow_data=True)
    written = [CANONICAL_OUT]
    write_json(CANONICAL_OUT, canonical)
    for alias in ALIAS_OUTS:
        payload = api_import if alias.name.endswith("api-import.json") else canonical
        write_json(alias, payload)
        written.append(alias)
    for flowdata_out in FLOWDATA_OUTS:
        write_json(flowdata_out, flow_data)
        written.append(flowdata_out)
    write_json(LIVE_FLOW_PATH, {"id": CHATFLOW_ID, "name": CHATFLOW_NAME, **flow_data})
    written.append(LIVE_FLOW_PATH)
    return written


def sync_live_db(flow_data: dict[str, Any]) -> Path:
    if not LIVE_DB_PATH.exists():
        raise FileNotFoundError(f"Flowise SQLite database not found: {LIVE_DB_PATH}")
    backup_path = LIVE_DB_PATH.with_suffix(f".sqlite.bak-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(LIVE_DB_PATH, backup_path)
    with sqlite3.connect(LIVE_DB_PATH) as conn:
        updated = conn.execute(
            """
            update chat_flow
               set name = ?,
                   flowData = ?,
                   deployed = 1,
                   isPublic = 1,
                   updatedDate = ?
             where id = ?
            """,
            (CHATFLOW_NAME, json.dumps(flow_data, separators=(",", ":")), datetime.now(timezone.utc).isoformat(), CHATFLOW_ID),
        ).rowcount
        if updated != 1:
            raise RuntimeError(f"Expected to update 1 chat_flow row for {CHATFLOW_ID}, updated {updated}")
        conn.commit()
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync-live-db", action="store_true")
    args = parser.parse_args()
    flow_data = build_flow_data()
    summary = validate_flow_data(flow_data)
    written = write_outputs(flow_data)
    result: dict[str, Any] = {"files": [str(path) for path in written], **summary, "live_chatflow_id": CHATFLOW_ID}
    if args.sync_live_db:
        result["flowise_db_backup"] = str(sync_live_db(flow_data))
        result["flowise_db_updated"] = True
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
