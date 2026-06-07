import os
from typing import Any

import requests
import streamlit as st


DEFAULT_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def api_url(path: str) -> str:
    return f"{st.session_state.backend_url.rstrip('/')}{path}"


def request_json(method: str, path: str, **kwargs: Any) -> Any:
    response = requests.request(method, api_url(path), timeout=120, **kwargs)
    if not response.ok:
        raise RuntimeError(response.text)
    return response.json()


st.set_page_config(page_title="Bank Credit AI POC", layout="wide")

if "backend_url" not in st.session_state:
    st.session_state.backend_url = DEFAULT_BACKEND_URL
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

st.sidebar.header("Settings")
st.session_state.backend_url = st.sidebar.text_input("Backend URL", st.session_state.backend_url)
st.sidebar.warning("Decision support only. Human credit officer review required.")

st.sidebar.header("LLM Provider")
provider_labels = {
    "OpenAI": "openai",
    "DeepSeek": "deepseek",
    "Custom Public API": "custom_public_api",
    "Local Mistral via Ollama": "local_mistral_ollama",
}
selected_provider_label = st.sidebar.selectbox("Provider", list(provider_labels.keys()))
selected_provider_value = provider_labels[selected_provider_label]
temperature = st.sidebar.slider("Temperature", min_value=0.0, max_value=1.0, value=0.2, step=0.05)
max_tokens = st.sidebar.number_input("Max tokens", min_value=128, max_value=8000, value=1200, step=100)

custom_base_url = None
custom_api_key = None
custom_model = None

if selected_provider_value == "openai":
    st.sidebar.info("Uses backend OPENAI_API_KEY and OPENAI_MODEL from .env")
elif selected_provider_value == "deepseek":
    st.sidebar.info("Uses backend DEEPSEEK_API_KEY and DEEPSEEK_MODEL from .env")
elif selected_provider_value == "local_mistral_ollama":
    st.sidebar.info("Requires Ollama running locally and model pulled: ollama pull mistral:7b-instruct")
else:
    st.sidebar.warning("Custom API keys are sent to the local FastAPI backend for this session. Do not use this POC with untrusted servers.")
    custom_base_url = st.sidebar.text_input(
        "Base URL",
        help=(
            "Examples: Mistral https://api.mistral.ai/v1, Together https://api.together.xyz/v1, "
            "Groq https://api.groq.com/openai/v1, OpenRouter https://openrouter.ai/api/v1, "
            "Fireworks https://api.fireworks.ai/inference/v1"
        ),
    )
    custom_api_key = st.sidebar.text_input("API Key", type="password")
    custom_model = st.sidebar.text_input("Model name", help="Example: mistral-small-latest")


def llm_payload(max_tokens_override: int | None = None) -> dict[str, Any]:
    payload = {
        "llm_provider": selected_provider_value,
        "temperature": temperature,
        "max_tokens": max_tokens_override or int(max_tokens),
    }
    if selected_provider_value == "custom_public_api":
        payload.update(
            {
                "custom_public_api_base_url": custom_base_url,
                "custom_public_api_key": custom_api_key,
                "custom_public_api_model": custom_model,
            }
        )
    return payload


CONNECTOR_FALLBACK = [
    {"label": "Manual Upload", "value": "manual_upload", "status": "available"},
    {"label": "S3", "value": "s3", "status": "available"},
    {"label": "SharePoint", "value": "sharepoint", "status": "placeholder"},
    {"label": "OpenText", "value": "opentext", "status": "placeholder"},
    {"label": "Hyland", "value": "hyland", "status": "placeholder"},
    {"label": "FileNet", "value": "filenet", "status": "placeholder"},
    {"label": "ServiceNow", "value": "servicenow", "status": "placeholder"},
    {"label": "Salesforce", "value": "salesforce", "status": "placeholder"},
    {"label": "Cloud Storage", "value": "cloud_storage", "status": "placeholder"},
]


def connector_options() -> list[dict[str, Any]]:
    try:
        return request_json("GET", "/connectors/options")["connectors"]
    except Exception:
        return CONNECTOR_FALLBACK


def placeholder_config(source_type: str) -> dict[str, Any]:
    if source_type == "sharepoint":
        return {
            "tenant_id": st.text_input("Tenant ID"),
            "client_id": st.text_input("Client ID"),
            "client_secret": st.text_input("Client Secret", type="password"),
            "site_id": st.text_input("Site ID"),
            "drive_id": st.text_input("Drive ID"),
            "folder_path": st.text_input("Folder Path"),
        }
    if source_type in {"opentext", "hyland"}:
        return {
            "base_url": st.text_input("Base URL"),
            "client_id": st.text_input("Client ID"),
            "client_secret": st.text_input("Client Secret", type="password"),
            "repository_id": st.text_input("Repository ID"),
        }
    if source_type == "filenet":
        return {
            "base_url": st.text_input("Base URL"),
            "username": st.text_input("Username"),
            "password": st.text_input("Password", type="password"),
            "object_store": st.text_input("Object Store"),
        }
    if source_type == "servicenow":
        return {
            "instance_url": st.text_input("Instance URL"),
            "username": st.text_input("Username"),
            "password": st.text_input("Password", type="password"),
            "table": st.text_input("Table", value="incident"),
            "record_sys_id": st.text_input("Attachment query or record sys_id optional"),
        }
    if source_type == "salesforce":
        return {
            "instance_url": st.text_input("Instance URL"),
            "client_id": st.text_input("Client ID"),
            "client_secret": st.text_input("Client Secret", type="password"),
            "username": st.text_input("Username"),
            "password": st.text_input("Password", type="password"),
            "security_token": st.text_input("Security Token", type="password"),
            "record_id": st.text_input("Object / Record ID optional"),
        }
    if source_type == "cloud_storage":
        return {
            "provider": st.selectbox("Provider", ["Azure Blob", "Google Cloud Storage", "MinIO", "Other"]),
            "endpoint": st.text_input("Endpoint"),
            "access_key": st.text_input("Access Key"),
            "secret_key": st.text_input("Secret Key", type="password"),
            "bucket": st.text_input("Bucket/Container"),
            "prefix": st.text_input("Prefix"),
        }
    return {}

st.title("Banking Credit Scoring Assistant POC")
st.caption("Decision support only. Human credit officer review required.")

left, right = st.columns([0.36, 0.64], gap="large")

with left:
    st.subheader("Customer Profile")
    with st.form("create_customer"):
        name = st.text_input("Name")
        customer_type = st.text_input("Customer type", value="business")
        industry = st.text_input("Industry")
        country = st.text_input("Country")
        submitted = st.form_submit_button("Create customer")
        if submitted:
            try:
                customer = request_json(
                    "POST",
                    "/customers",
                    json={
                        "name": name,
                        "customer_type": customer_type,
                        "industry": industry or None,
                        "country": country or None,
                    },
                )
                st.success(f"Created customer #{customer['id']}")
            except Exception as exc:
                st.error(f"Could not create customer: {exc}")

    try:
        customers = request_json("GET", "/customers")
    except Exception:
        customers = []

    customer_options = {f"{item['id']} - {item['name']}": item["id"] for item in customers}
    selected_label = st.selectbox("Select customer", list(customer_options.keys()) or ["No customers yet"])
    selected_customer_id = customer_options.get(selected_label)

    st.subheader("Documents")
    options = connector_options()
    connector_labels = {item["label"]: item["value"] for item in options}
    selected_source_label = st.selectbox("Data Store Source", list(connector_labels.keys()))
    selected_source_type = connector_labels[selected_source_label]

    if selected_source_type == "manual_upload":
        uploaded_files = st.file_uploader(
            "Upload credit documents",
            type=["pdf", "txt", "csv", "xlsx", "xls"],
            accept_multiple_files=True,
        )
        document_type = st.text_input("Document type", value="customer_credit_document")

        if st.button("Upload documents", disabled=not selected_customer_id or not uploaded_files):
            for uploaded_file in uploaded_files or []:
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    data = {"customer_id": selected_customer_id, "document_type": document_type}
                    result = request_json("POST", "/documents/upload", files=files, data=data)
                    st.success(f"Uploaded {result['filename']} as document #{result['id']}")
                except Exception as exc:
                    st.error(f"Upload failed for {uploaded_file.name}: {exc}")
    elif selected_source_type == "s3":
        st.caption("Import from AWS S3 or S3-compatible storage such as MinIO.")
        s3_config = {
            "endpoint_url": st.text_input("Endpoint URL optional"),
            "access_key_id": st.text_input("Access Key ID optional"),
            "secret_access_key": st.text_input("Secret Access Key optional", type="password"),
            "region": st.text_input("Region", value="us-east-1"),
            "bucket": st.text_input("Bucket"),
            "prefix": st.text_input("Prefix"),
        }

        if st.button("Test Connection", disabled=not s3_config["bucket"]):
            try:
                result = request_json("POST", "/connectors/test", json={"source_type": "s3", "config": s3_config})
                (st.success if result["success"] else st.error)(result["message"])
            except Exception as exc:
                st.error(f"S3 test failed: {exc}")

        if st.button("List Documents", disabled=not s3_config["bucket"]):
            try:
                result = request_json("POST", "/connectors/list-documents", json={"source_type": "s3", "config": s3_config})
                st.session_state.s3_documents = result["documents"]
                st.success(result["message"])
            except Exception as exc:
                st.error(f"S3 list failed: {exc}")

        s3_documents = st.session_state.get("s3_documents", [])
        if s3_documents:
            st.dataframe(
                [
                    {
                        "filename": doc["filename"],
                        "size": doc.get("size_bytes"),
                        "last_modified": doc.get("last_modified"),
                        "source_uri": doc["source_uri"],
                    }
                    for doc in s3_documents
                ],
                hide_index=True,
                use_container_width=True,
            )
            labels = {f"{doc['filename']} - {doc['source_uri']}": doc for doc in s3_documents}
            selected_doc_label = st.selectbox("Select S3 document", list(labels.keys()))
            selected_doc = labels[selected_doc_label]
            if st.button("Ingest Selected Document", disabled=not selected_customer_id):
                try:
                    result = request_json(
                        "POST",
                        "/connectors/ingest",
                        json={
                            "source_type": "s3",
                            "customer_id": selected_customer_id,
                            "external_document_id": selected_doc["external_document_id"],
                            "source_uri": selected_doc["source_uri"],
                            "filename": selected_doc["filename"],
                            "config": s3_config,
                        },
                    )
                    st.success(result["message"])
                except Exception as exc:
                    st.error(f"S3 ingest failed: {exc}")
    else:
        st.info("This connector interface is prepared for enterprise integration. Full API implementation is not enabled in this POC yet.")
        config = placeholder_config(selected_source_type)
        if st.button("Test Connector Placeholder"):
            try:
                result = request_json(
                    "POST",
                    "/connectors/test",
                    json={"source_type": selected_source_type, "config": config},
                )
                st.warning(result["message"])
                st.json(result.get("details", {}), expanded=False)
            except Exception as exc:
                st.error(f"Connector test failed: {exc}")

    documents = []
    if selected_customer_id:
        try:
            documents = request_json("GET", f"/documents?customer_id={selected_customer_id}")
        except Exception as exc:
            st.error(f"Could not load documents: {exc}")

    if documents:
        st.dataframe(
            [{"id": doc["id"], "filename": doc["filename"], "type": doc["document_type"], "status": doc["status"]} for doc in documents],
            hide_index=True,
            use_container_width=True,
        )
        ingest_ids = st.multiselect("Documents to ingest", [doc["id"] for doc in documents])
        if st.button("Ingest selected documents", disabled=not ingest_ids):
            for document_id in ingest_ids:
                try:
                    result = request_json("POST", f"/ingest/{document_id}")
                    st.success(f"Ingested document #{document_id}: {result['chunks_created']} chunks")
                except Exception as exc:
                    st.error(f"Ingestion failed for document #{document_id}: {exc}")

with right:
    st.subheader("Chat")
    if not selected_customer_id:
        st.info("Create or select a customer to start chatting.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask about the customer's credit risk, documents, or missing information")
    if prompt and selected_customer_id:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            response = request_json(
                "POST",
                "/chat",
                json={
                    "customer_id": selected_customer_id,
                    "message": prompt,
                    "session_id": st.session_state.session_id,
                    **llm_payload(),
                },
            )
            st.session_state.session_id = response["session_id"]
            answer = response["answer"]
            st.session_state.messages.append({"role": "assistant", "content": answer})
            with st.chat_message("assistant"):
                st.markdown(answer)
                if response.get("citations"):
                    st.caption("Citations")
                    st.json(response["citations"], expanded=False)
                st.caption(
                    f"Provider: {response.get('llm_provider_used')} | Model: {response.get('llm_model_used')} | "
                    f"Flowise used: {response.get('flowise_used')} | Fallback used: {response.get('fallback_used')}"
                )
        except Exception as exc:
            st.error(f"Chat failed: {exc}")

    st.subheader("Credit Assessment")
    if st.button("Generate credit assessment", disabled=not selected_customer_id):
        try:
            assessment = request_json("POST", f"/credit-assessment/{selected_customer_id}", json=llm_payload(max_tokens_override=1500))
            st.markdown(assessment["answer"])
            st.metric("Preliminary heuristic score", assessment["heuristic_score"])
            st.write(f"Heuristic risk level: {assessment['heuristic_risk_level']}")
            st.write("Positive signals", assessment["matched_positive_signals"])
            st.write("Negative signals", assessment["matched_negative_signals"])
            st.caption("Citations")
            st.json(assessment["citations"], expanded=False)
            st.caption(
                f"Provider: {assessment.get('llm_provider_used')} | Model: {assessment.get('llm_model_used')} | "
                f"Flowise used: {assessment.get('flowise_used')} | Fallback used: {assessment.get('fallback_used')}"
            )
        except Exception as exc:
            st.error(f"Assessment failed: {exc}")
