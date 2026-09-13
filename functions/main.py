import asyncio
import os
import uuid

from asgiref.sync import async_to_sync
from firebase_admin import initialize_app, credentials
from firebase_functions import https_fn, scheduler_fn, tasks_fn
from sqlalchemy import text
from firebase_functions.options import (
    MemoryOption,
    RateLimits,
    RetryConfig,
    set_global_options,
)


from app.core.config import settings
from app.jobs.cleanup_job import run_cleanup
from app.main import app as fastapi_app
from app.pipeline.pipeline import PipelineError, run_pipeline
from app.pipeline.youtube_downloader import UnsupportedVideoError, VideoTooLongError
from app.db.session import AsyncSessionLocal
from app.integration.embedding_client import embed_text

set_global_options(
    max_instances=10,
    memory=MemoryOption.GB_2,
    cpu=1,
    timeout_sec=300,
)

if settings.google_credentials_path and os.path.exists(settings.google_credentials_path):
    initialize_app(credentials.Certificate(settings.google_credentials_path))
else:
    initialize_app()


async def _warm_reusable_resources() -> None:
    """Prime resources that are reused by every analysis in this instance.

    External work (YouTube download and Groq requests) is deliberately excluded:
    it is per-video work, costs money, and cannot be cached safely.  The small
    embedding call both loads the bundled model and verifies it can run.
    """
    await embed_text("warmup")
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))


def _wsgi_app(environ, start_response):
    """
    Minimal WSGI-compatible callable that drives the FastAPI (ASGI)
    app synchronously via asgiref, in the same thread that Cloud Run
    is already giving CPU time to for this request — no extra
    background thread/event loop like a2wsgi spins up.
    """
    body = environ["wsgi.input"].read(int(environ.get("CONTENT_LENGTH") or 0))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": environ["REQUEST_METHOD"],
        "scheme": environ.get("wsgi.url_scheme", "https"),
        "path": environ.get("PATH_INFO", ""),
        "raw_path": environ.get("PATH_INFO", "").encode("utf-8"),
        "query_string": environ.get("QUERY_STRING", "").encode("utf-8"),
        "root_path": "",
        "headers": [
            (k[5:].replace("_", "-").lower().encode(), v.encode())
            for k, v in environ.items()
            if k.startswith("HTTP_")
        ]
        + (
            [(b"content-type", environ["CONTENT_TYPE"].encode())]
            if environ.get("CONTENT_TYPE")
            else []
        )
        + (
            [(b"content-length", environ["CONTENT_LENGTH"].encode())]
            if environ.get("CONTENT_LENGTH")
            else []
        ),
        "client": (environ.get("REMOTE_ADDR", ""), 0),
        "server": (environ.get("SERVER_NAME", ""), int(environ.get("SERVER_PORT") or 0)),
    }

    response = {"status": 200, "headers": [], "body": b""}
    body_sent = {"done": False}

    async def receive():
        if body_sent["done"]:
            return {"type": "http.disconnect"}
        body_sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            response["status"] = message["status"]
            response["headers"] = message["headers"]
        elif message["type"] == "http.response.body":
            response["body"] += message.get("body", b"")

    async_to_sync(fastapi_app)(scope, receive, send)

    headers = [(k.decode(), v.decode()) for k, v in response["headers"]]
    start_response(f"{response['status']} OK", headers)
    return [response["body"]]


@https_fn.on_request(
    concurrency=2,
    secrets=["GROQ_API_KEY", "GROQ_API_KEY_FALLBACK", "DATABASE_URL", "RECAPTCHA_SECRET_KEY"],
)
def api(req: https_fn.Request) -> https_fn.Response:
    # Prime the costly reusable resources without downloading a video or
    # invoking Groq. The resources stay cached only while this autoscaled
    # instance remains alive; it may later scale to zero when idle.
    if req.method == "POST" and req.args.get("warmup", "").lower() == "true":
        asyncio.run(_warm_reusable_resources())
        return https_fn.Response(
            '{"warm":true}',
            status=200,
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    return https_fn.Response.from_app(_wsgi_app, req.environ)


@https_fn.on_request()
def ping(req: https_fn.Request) -> https_fn.Response:
    return https_fn.Response("pong", status=200)


async def _process_video(data: dict) -> None:
    video_id = data.get("video_id")
    youtube_url = data.get("youtube_url")
    if not video_id or not youtube_url:
        raise ValueError("Task payload requires video_id and youtube_url.")

    async with AsyncSessionLocal() as db:
        await run_pipeline(uuid.UUID(video_id), youtube_url, db=db)


@tasks_fn.on_task_dispatched(
    secrets=["GROQ_API_KEY", "GROQ_API_KEY_FALLBACK", "DATABASE_URL"],
    retry_config=RetryConfig(max_attempts=1),
    rate_limits=RateLimits(max_concurrent_dispatches=3),
)
def processvideo(request) -> None:
    try:
        asyncio.run(_process_video(request.data))
    except PipelineError as exc:
        # Duration violations are permanent input errors; retrying would only
        # repeat the same metadata lookup. Transient failures remain retryable.
        if isinstance(exc.__cause__, (VideoTooLongError, UnsupportedVideoError)):
            return
        raise


@scheduler_fn.on_schedule(
    schedule="every 24 hours", secrets=["GROQ_API_KEY", "DATABASE_URL"]
)
def cleanup_expired_videos(event: scheduler_fn.ScheduledEvent) -> None:
    asyncio.run(run_cleanup())
