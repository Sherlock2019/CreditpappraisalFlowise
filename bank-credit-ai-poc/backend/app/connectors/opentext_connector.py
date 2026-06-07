from app.connectors.placeholder import PlaceholderConnector


class OpenTextConnector(PlaceholderConnector):
    source_type = "opentext"
    label = "OpenText"
    required_fields = ("base_url", "client_id", "client_secret", "repository_id")
    future_method = "OpenText REST API or CMIS using client credentials or token and repository_id."
