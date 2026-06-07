from app.connectors.base import BaseConnector


class ManualUploadConnector(BaseConnector):
    source_type = "manual_upload"
    label = "Manual Upload"

    def test_connection(self, config: dict | None = None) -> dict:
        return {"success": True, "message": "Manual upload is available.", "details": {}}

    def list_documents(self, config: dict | None = None) -> list[dict]:
        return []

    def download_document(
        self,
        external_document_id: str | None = None,
        source_uri: str | None = None,
        config: dict | None = None,
    ) -> tuple[bytes, dict]:
        raise NotImplementedError("Use /documents/upload for manual uploads.")
