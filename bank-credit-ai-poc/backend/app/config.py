from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://credit_ai_user:credit_ai_password@postgres:5432/credit_ai"
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    llm_provider: str = "openai"
    openai_model: str = "gpt-4o-mini"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    custom_public_api_base_url: str | None = None
    custom_public_api_key: str | None = None
    custom_public_api_model: str | None = None
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "mistral:7b-instruct"
    dev_allow_insecure_custom_api: bool = False
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"
    flowise_base_url: str = ""
    flowise_api_url: str = "http://flowise:3000"
    flowise_api_key: str = ""
    flowise_chatflow_id: str = ""
    poc_backend_base_url: str = "http://localhost:8000"
    custom_llm_base_url: str | None = None
    custom_llm_api_key: str | None = None
    custom_llm_model: str | None = None
    ollama_local_model: str = "mistral"
    default_base_interest_rate_pct: float = 8.5
    default_loan_term_months: int = 60
    audit_log_dir: str = "/app/data/audit_logs"
    workflow_state_dir: str = "/app/data/workflow_state"
    email_draft_dir: str = "/app/data/email_drafts"
    upload_dir: str = "/app/data/uploads"
    demo_customer_documents_dir: str = "/app/demo/customer_documents"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str | None = None
    s3_prefix: str | None = None
    s3_use_ssl: bool = True
    sharepoint_tenant_id: str | None = None
    sharepoint_client_id: str | None = None
    sharepoint_client_secret: str | None = None
    sharepoint_site_id: str | None = None
    sharepoint_drive_id: str | None = None
    sharepoint_folder_path: str | None = None
    opentext_base_url: str | None = None
    opentext_client_id: str | None = None
    opentext_client_secret: str | None = None
    opentext_repository_id: str | None = None
    hyland_base_url: str | None = None
    hyland_client_id: str | None = None
    hyland_client_secret: str | None = None
    hyland_repository_id: str | None = None
    filenet_base_url: str | None = None
    filenet_username: str | None = None
    filenet_password: str | None = None
    filenet_object_store: str | None = None
    servicenow_instance_url: str | None = None
    servicenow_username: str | None = None
    servicenow_password: str | None = None
    servicenow_table: str = "incident"
    salesforce_instance_url: str | None = None
    salesforce_client_id: str | None = None
    salesforce_client_secret: str | None = None
    salesforce_username: str | None = None
    salesforce_password: str | None = None
    salesforce_security_token: str | None = None
    cloud_storage_provider: str | None = None
    cloud_storage_endpoint: str | None = None
    cloud_storage_access_key: str | None = None
    cloud_storage_secret_key: str | None = None
    cloud_storage_bucket: str | None = None
    cloud_storage_prefix: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
