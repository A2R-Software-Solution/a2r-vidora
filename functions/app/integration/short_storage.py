"""Private objects with short-lived signed access; never expose bucket credentials."""
import asyncio
from datetime import timedelta
import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage
from google.api_core.exceptions import NotFound
from app.core.config import settings


def _blob(name):
    if not settings.shorts_bucket:
        raise RuntimeError("SHORTS_BUCKET is required.")
    return storage.Client(project=settings.gcp_project_id).bucket(settings.shorts_bucket).blob(name)


async def upload(name, path):
    await asyncio.to_thread(_blob(name).upload_from_filename, str(path), content_type="video/mp4", timeout=60)


async def delete(name):
    try:
        await asyncio.to_thread(_blob(name).delete, timeout=30)
    except NotFound:
        pass


def _signed_url(name, download, valid_for):
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    options = {}
    if settings.shorts_signer_email:
        credentials.refresh(Request())
        options = {"service_account_email": settings.shorts_signer_email, "access_token": credentials.token}
    return _blob(name).generate_signed_url(
        version="v4", expiration=timedelta(seconds=valid_for), method="GET", credentials=credentials,
        response_disposition=f'{"attachment" if download else "inline"}; filename="vidora-short.mp4"', **options)


async def signed_url(name, *, download=True, valid_for=600):
    return await asyncio.to_thread(_signed_url, name, download, valid_for)
