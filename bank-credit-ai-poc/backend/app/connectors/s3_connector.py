from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from app.config import get_settings
from app.connectors.base import BaseConnector


class S3Connector(BaseConnector):
    source_type = "s3"
    label = "S3"

    def _setting(self, config: dict, key: str, fallback_name: str):
        value = config.get(key)
        if value not in (None, ""):
            return value
        return getattr(get_settings(), fallback_name)

    def _client_and_scope(self, config: dict | None = None):
        config = config or {}
        settings = get_settings()
        bucket = self._setting(config, "bucket", "s3_bucket")
        prefix = self._setting(config, "prefix", "s3_prefix") or ""
        if not bucket:
            raise ValueError("S3 bucket is required.")

        kwargs = {
            "region_name": self._setting(config, "region", "s3_region") or "us-east-1",
            "use_ssl": bool(config.get("use_ssl", settings.s3_use_ssl)),
        }
        endpoint_url = self._setting(config, "endpoint_url", "s3_endpoint_url")
        access_key = self._setting(config, "access_key_id", "s3_access_key_id")
        secret_key = self._setting(config, "secret_access_key", "s3_secret_access_key")
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key

        return boto3.client("s3", **kwargs), bucket, prefix

    def _clear_error(self, exc: Exception) -> str:
        if isinstance(exc, NoCredentialsError):
            return "S3 credentials were not found. Provide keys or configure IAM/default credentials."
        if isinstance(exc, EndpointConnectionError):
            return "S3 endpoint unavailable. Check endpoint URL."
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"AccessDenied", "403"}:
                return "S3 access denied. Check credentials and bucket permissions."
            if code in {"NoSuchBucket", "404"}:
                return "S3 bucket not found. Check bucket name."
            return f"S3 error: {code or exc}"
        return str(exc)

    def test_connection(self, config: dict | None = None) -> dict:
        try:
            client, bucket, prefix = self._client_and_scope(config)
            client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
            return {"success": True, "message": "S3 connection successful.", "details": {"bucket": bucket, "prefix": prefix}}
        except Exception as exc:
            return {"success": False, "message": self._clear_error(exc), "details": {}}

    def list_documents(self, config: dict | None = None) -> list[dict]:
        try:
            client, bucket, prefix = self._client_and_scope(config)
            paginator = client.get_paginator("list_objects_v2")
            documents = []
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    key = item["Key"]
                    if key.endswith("/"):
                        continue
                    content_type = None
                    try:
                        content_type = client.head_object(Bucket=bucket, Key=key).get("ContentType")
                    except ClientError:
                        content_type = None
                    documents.append(
                        {
                            "external_document_id": key,
                            "filename": Path(key).name,
                            "source_uri": f"s3://{bucket}/{key}",
                            "size_bytes": item.get("Size"),
                            "last_modified": item.get("LastModified").isoformat() if item.get("LastModified") else None,
                            "content_type": content_type,
                            "metadata": {"bucket": bucket, "key": key},
                        }
                    )
            return documents
        except Exception as exc:
            raise RuntimeError(self._clear_error(exc)) from exc

    def download_document(
        self,
        external_document_id: str | None = None,
        source_uri: str | None = None,
        config: dict | None = None,
    ) -> tuple[bytes, dict]:
        try:
            client, bucket, _ = self._client_and_scope(config)
            key = external_document_id
            if source_uri:
                parsed = urlparse(source_uri)
                if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
                    raise ValueError("S3 source_uri must be formatted as s3://bucket/key")
                bucket = parsed.netloc
                key = parsed.path.lstrip("/")
            if not key:
                raise ValueError("S3 external_document_id or source_uri is required.")

            obj = client.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read()
            metadata = {
                "filename": Path(key).name,
                "content_type": obj.get("ContentType"),
                "source_uri": f"s3://{bucket}/{key}",
                "external_document_id": key,
                "source_type": self.source_type,
                "size_bytes": obj.get("ContentLength"),
                "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None,
                "bucket": bucket,
                "key": key,
            }
            return body, metadata
        except Exception as exc:
            raise RuntimeError(self._clear_error(exc)) from exc
