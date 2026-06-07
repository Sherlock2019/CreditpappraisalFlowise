from app.connectors.placeholder import PlaceholderConnector


class CloudStorageConnector(PlaceholderConnector):
    source_type = "cloud_storage"
    label = "Cloud Storage"
    required_fields = ("provider", "endpoint", "access_key", "secret_key", "bucket", "prefix")
    future_method = "Generic connector for Azure Blob, Google Cloud Storage, MinIO, or other object storage APIs."
