"""Blob storage package.

Provides S3-compatible object storage helpers for attachments and photos.
All public functions are no-ops when boto3 is not installed or BLOB_S3_BUCKET
is not configured.
"""
