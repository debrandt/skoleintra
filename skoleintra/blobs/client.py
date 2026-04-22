"""S3-compatible storage client helpers."""

from __future__ import annotations

import logging
import mimetypes

from skoleintra.settings import Settings

logger = logging.getLogger(__name__)

try:
    import boto3  # type: ignore[import-untyped]
    _HAS_BOTO3 = True
except ImportError:
    _HAS_BOTO3 = False


def get_s3_client(settings: Settings):
    """Return a configured boto3 S3 client, or *None* if not available/configured.

    Returns None when:
    - boto3 is not installed
    - BLOB_S3_BUCKET is not set
    """
    if not _HAS_BOTO3:
        logger.warning("boto3 is not installed; blob storage is disabled")
        return None
    if not settings.blob_s3_bucket:
        return None

    kwargs: dict = {"region_name": settings.blob_s3_region}
    if settings.blob_s3_access_key_id:
        kwargs["aws_access_key_id"] = settings.blob_s3_access_key_id
    if settings.blob_s3_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.blob_s3_secret_access_key
    if settings.blob_s3_endpoint_url:
        kwargs["endpoint_url"] = settings.blob_s3_endpoint_url

    return boto3.client("s3", **kwargs)


def upload_blob(s3_client, bucket: str, key: str, data: bytes, content_type: str) -> None:
    s3_client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def download_blob(s3_client, bucket: str, key: str) -> bytes:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def generate_presigned_url(s3_client, bucket: str, key: str, expires_in: int = 86400) -> str:
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def guess_content_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"
