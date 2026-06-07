from app.connectors.placeholder import PlaceholderConnector


class ServiceNowConnector(PlaceholderConnector):
    source_type = "servicenow"
    label = "ServiceNow"
    required_fields = ("instance_url", "username", "password", "table")
    future_method = "ServiceNow REST API plus Attachment API using username/password or OAuth."
