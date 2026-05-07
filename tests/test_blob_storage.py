from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from skoleintra.blobs.client import (
    download_blob,
    generate_presigned_url,
    get_s3_client,
    upload_blob,
)
from skoleintra.settings import Settings


def _wait_for_minio(
    endpoint_url: str, process: subprocess.Popen[bytes], log_path: Path
) -> None:
    deadline = time.time() + 10
    health_url = f"{endpoint_url}/minio/health/live"
    while time.time() < deadline:
        if process.poll() is not None:
            raise AssertionError(log_path.read_text(encoding="utf-8"))
        try:
            with urllib.request.urlopen(health_url, timeout=1):
                return
        except urllib.error.URLError:
            time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for MinIO at {endpoint_url}")


@pytest.fixture
def minio_s3_client(
    tmp_path_factory: pytest.TempPathFactory, free_tcp_port_factory: Callable[[], int]
):
    minio = shutil.which("minio")
    if minio is None:
        pytest.skip("minio binary not available")

    port = free_tcp_port_factory()
    data_dir = tmp_path_factory.mktemp("minio-data")
    log_path = data_dir / "minio.log"
    endpoint_url = f"http://127.0.0.1:{port}"
    env = os.environ | {
        "MINIO_ROOT_USER": "minioadmin",
        "MINIO_ROOT_PASSWORD": "minioadmin",
        "MINIO_BROWSER": "off",
    }

    with log_path.open("wb") as log_file:
        with subprocess.Popen(
            [minio, "server", "--address", f"127.0.0.1:{port}", str(data_dir)],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        ) as process:
            try:
                _wait_for_minio(endpoint_url, process, log_path)
                settings = Settings(
                    blob_s3_bucket="attachments-test",
                    blob_s3_endpoint_url=endpoint_url,
                    blob_s3_access_key_id="minioadmin",
                    blob_s3_secret_access_key="minioadmin",
                )
                s3_client = get_s3_client(settings)
                assert s3_client is not None
                s3_client.create_bucket(Bucket=settings.blob_s3_bucket)
                yield s3_client, settings.blob_s3_bucket
            finally:
                process.terminate()
                process.wait(timeout=5)


def test_upload_and_download_blob_content(minio_s3_client):
    s3_client, bucket = minio_s3_client

    upload_blob(
        s3_client,
        bucket,
        "attachments/message-1.txt",
        b"hello from minio",
        "text/plain",
    )

    assert (
        download_blob(s3_client, bucket, "attachments/message-1.txt")
        == b"hello from minio"
    )


def test_generate_presigned_url_targets_uploaded_object(minio_s3_client):
    s3_client, bucket = minio_s3_client
    key = "attachments/message-2.txt"
    upload_blob(s3_client, bucket, key, b"presign me", "text/plain")

    presigned_url = generate_presigned_url(s3_client, bucket, key, expires_in=60)
    parsed_url = urlparse(presigned_url)
    endpoint_url = urlparse(s3_client.meta.endpoint_url)
    query_params = parse_qs(parsed_url.query)

    assert parsed_url.netloc == endpoint_url.netloc
    assert bucket in unquote(parsed_url.path)
    assert key in unquote(parsed_url.path)
    assert "Expires" in query_params or "X-Amz-Expires" in query_params


def test_get_s3_client_returns_none_without_bucket():
    settings = Settings()

    assert get_s3_client(settings) is None
