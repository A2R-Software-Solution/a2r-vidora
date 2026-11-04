"""Private Media Downloader results with short-lived signed download links."""
import asyncio
from datetime import timedelta
import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage
from google.api_core.exceptions import NotFound
from app.core.config import settings

CONTENT_TYPES = {"mp3": "audio/mpeg", "mp4": "video/mp4"}


def _blob(name):
    if not settings.media_download_bucket:
        raise RuntimeError("MEDIA_DOWNLOAD_BUCKET is required.")
    return storage.Client(project=settings.gcp_project_id).bucket(settings.media_download_bucket).blob(name)


async def upload(name, path, extension):
    await asyncio.to_thread(_blob(name).upload_from_filename, str(path),
                            content_type=CONTENT_TYPES[extension], timeout=300)


async def delete(name):
    try:
        await asyncio.to_thread(_blob(name).delete, timeout=30)
    except NotFound:
        pass


def _signed_url(name, filename, extension, valid_for):
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    options = {}
    signer = settings.media_download_signer_email or settings.audio_merge_signer_email or settings.shorts_signer_email
    if signer:
        credentials.refresh(Request())
        options = {"service_account_email": signer, "access_token": credentials.token}
    return _blob(name).generate_signed_url(
        version="v4", expiration=timedelta(seconds=valid_for), method="GET", credentials=credentials,
        response_type=CONTENT_TYPES[extension],
        response_disposition=f'attachment; filename="{filename}"',
        **options)


async def signed_url(name, filename, extension, *, valid_for=600):
    return await asyncio.to_thread(_signed_url, name, filename, extension, valid_for)
