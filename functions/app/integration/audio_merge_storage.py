"""Private Song Merger objects (uploads and results) with short-lived signed access."""
import asyncio
from datetime import timedelta
import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage
from google.api_core.exceptions import NotFound
from app.core.config import settings

CONTENT_TYPES = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}


def _blob(name):
    if not settings.audio_merge_bucket:
        raise RuntimeError("AUDIO_MERGE_BUCKET is required.")
    return storage.Client(project=settings.gcp_project_id).bucket(settings.audio_merge_bucket).blob(name)


async def upload_bytes(name, data: bytes):
    await asyncio.to_thread(_blob(name).upload_from_string, data, content_type="application/octet-stream", timeout=60)


async def upload(name, path, output_format):
    await asyncio.to_thread(_blob(name).upload_from_filename, str(path),
                            content_type=CONTENT_TYPES[output_format], timeout=60)


async def download(name, path):
    await asyncio.to_thread(_blob(name).download_to_filename, str(path), timeout=60)


async def delete(name):
    try:
        await asyncio.to_thread(_blob(name).delete, timeout=30)
    except NotFound:
        pass


def _signed_url(name, download, valid_for, output_format):
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    options = {}
    signer = settings.audio_merge_signer_email or settings.shorts_signer_email
    if signer:
        credentials.refresh(Request())
        options = {"service_account_email": signer, "access_token": credentials.token}
    return _blob(name).generate_signed_url(
        version="v4", expiration=timedelta(seconds=valid_for), method="GET", credentials=credentials,
        response_type=CONTENT_TYPES[output_format],
        response_disposition=f'{"attachment" if download else "inline"}; filename="vidora-merged.{output_format}"',
        **options)


async def signed_url(name, output_format, *, download=True, valid_for=600):
    return await asyncio.to_thread(_signed_url, name, download, valid_for, output_format)
