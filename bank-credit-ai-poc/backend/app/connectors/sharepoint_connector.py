from app.connectors.placeholder import PlaceholderConnector


class SharePointConnector(PlaceholderConnector):
    source_type = "sharepoint"
    label = "SharePoint"
    required_fields = ("tenant_id", "client_id", "client_secret", "site_id", "drive_id", "folder_path")
    future_method = "Microsoft Graph API with OAuth2 client credentials to list and download drive items."
