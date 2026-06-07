from app.connectors.placeholder import PlaceholderConnector


class SalesforceConnector(PlaceholderConnector):
    source_type = "salesforce"
    label = "Salesforce"
    required_fields = ("instance_url", "client_id", "client_secret", "username", "password", "security_token")
    future_method = "Salesforce REST API using OAuth connected app and ContentDocument/ContentVersion or Attachment objects."
