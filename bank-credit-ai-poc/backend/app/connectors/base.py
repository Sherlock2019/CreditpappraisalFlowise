class BaseConnector:
    source_type: str
    label: str

    def test_connection(self, config: dict | None = None) -> dict:
        raise NotImplementedError

    def list_documents(self, config: dict | None = None) -> list[dict]:
        raise NotImplementedError

    def download_document(
        self,
        external_document_id: str | None = None,
        source_uri: str | None = None,
        config: dict | None = None,
    ) -> tuple[bytes, dict]:
        raise NotImplementedError
