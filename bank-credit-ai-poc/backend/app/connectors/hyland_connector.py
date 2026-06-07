from app.connectors.placeholder import PlaceholderConnector


class HylandConnector(PlaceholderConnector):
    source_type = "hyland"
    label = "Hyland"
    required_fields = ("base_url", "client_id", "client_secret", "repository_id")
    future_method = "Hyland OnBase APIs or vendor SDK using OAuth/client credentials and repository or document type."
