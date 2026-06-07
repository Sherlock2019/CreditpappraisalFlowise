from fastapi import HTTPException

from app.connectors.base import BaseConnector
from app.connectors.cloud_storage_connector import CloudStorageConnector
from app.connectors.filenet_connector import FileNetConnector
from app.connectors.hyland_connector import HylandConnector
from app.connectors.manual_upload_connector import ManualUploadConnector
from app.connectors.opentext_connector import OpenTextConnector
from app.connectors.s3_connector import S3Connector
from app.connectors.salesforce_connector import SalesforceConnector
from app.connectors.servicenow_connector import ServiceNowConnector
from app.connectors.sharepoint_connector import SharePointConnector


SOURCE_ALIASES = {
    "manual upload": "manual_upload",
    "Manual Upload": "manual_upload",
    "manual_upload": "manual_upload",
    "s3": "s3",
    "S3": "s3",
    "sharepoint": "sharepoint",
    "SharePoint": "sharepoint",
    "opentext": "opentext",
    "OpenText": "opentext",
    "hyland": "hyland",
    "Hyland": "hyland",
    "filenet": "filenet",
    "FileNet": "filenet",
    "servicenow": "servicenow",
    "ServiceNow": "servicenow",
    "salesforce": "salesforce",
    "Salesforce": "salesforce",
    "cloud storage": "cloud_storage",
    "Cloud Storage": "cloud_storage",
    "cloud_storage": "cloud_storage",
}


def normalize_source_type(source_type: str) -> str:
    if not source_type:
        raise HTTPException(status_code=400, detail="source_type is required")
    return SOURCE_ALIASES.get(source_type, SOURCE_ALIASES.get(source_type.strip().lower(), source_type.strip().lower()))


def get_connector(source_type: str) -> BaseConnector:
    normalized = normalize_source_type(source_type)
    connectors: dict[str, BaseConnector] = {
        "manual_upload": ManualUploadConnector(),
        "s3": S3Connector(),
        "sharepoint": SharePointConnector(),
        "opentext": OpenTextConnector(),
        "hyland": HylandConnector(),
        "filenet": FileNetConnector(),
        "servicenow": ServiceNowConnector(),
        "salesforce": SalesforceConnector(),
        "cloud_storage": CloudStorageConnector(),
    }
    connector = connectors.get(normalized)
    if not connector:
        raise HTTPException(status_code=400, detail=f"Unsupported source_type: {source_type}")
    return connector


def get_connector_options() -> list[dict[str, str]]:
    return [
        {
            "label": "Manual Upload",
            "value": "manual_upload",
            "status": "available",
            "description": "Upload credit documents directly from the Web UI.",
        },
        {
            "label": "S3",
            "value": "s3",
            "status": "available",
            "description": "Import documents from AWS S3 or S3-compatible storage such as MinIO.",
        },
        {
            "label": "SharePoint",
            "value": "sharepoint",
            "status": "placeholder",
            "description": "Future connector using Microsoft Graph API.",
        },
        {
            "label": "OpenText",
            "value": "opentext",
            "status": "placeholder",
            "description": "Future connector using OpenText REST API or CMIS.",
        },
        {
            "label": "Hyland",
            "value": "hyland",
            "status": "placeholder",
            "description": "Future connector using Hyland OnBase APIs or vendor SDK.",
        },
        {
            "label": "FileNet",
            "value": "filenet",
            "status": "placeholder",
            "description": "Future connector using IBM FileNet APIs, CMIS, or vendor SDK.",
        },
        {
            "label": "ServiceNow",
            "value": "servicenow",
            "status": "placeholder",
            "description": "Future connector using ServiceNow REST and Attachment APIs.",
        },
        {
            "label": "Salesforce",
            "value": "salesforce",
            "status": "placeholder",
            "description": "Future connector using Salesforce ContentDocument/ContentVersion APIs.",
        },
        {
            "label": "Cloud Storage",
            "value": "cloud_storage",
            "status": "placeholder",
            "description": "Future generic connector for Azure Blob, Google Cloud Storage, MinIO, or other object storage.",
        },
    ]
