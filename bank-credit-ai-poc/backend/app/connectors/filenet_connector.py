from app.connectors.placeholder import PlaceholderConnector


class FileNetConnector(PlaceholderConnector):
    source_type = "filenet"
    label = "FileNet"
    required_fields = ("base_url", "username", "password", "object_store")
    future_method = "IBM FileNet API, CMIS, or vendor SDK using object store and username/password or OAuth."
