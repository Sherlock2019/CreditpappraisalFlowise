from app.connectors.base import BaseConnector


class PlaceholderConnector(BaseConnector):
    required_fields: tuple[str, ...] = ()
    future_method: str = ""

    def _missing(self, config: dict | None) -> list[str]:
        config = config or {}
        return [field for field in self.required_fields if not config.get(field)]

    def test_connection(self, config: dict | None = None) -> dict:
        missing = self._missing(config)
        details = {"required_fields": list(self.required_fields), "missing_fields": missing, "future_method": self.future_method}
        return {
            "success": False,
            "message": f"{self.label} connector placeholder created. Real API integration not implemented yet.",
            "details": details,
        }

    def list_documents(self, config: dict | None = None) -> list[dict]:
        return []

    def download_document(
        self,
        external_document_id: str | None = None,
        source_uri: str | None = None,
        config: dict | None = None,
    ) -> tuple[bytes, dict]:
        raise NotImplementedError(f"{self.label} download is not implemented yet. Future method: {self.future_method}")
