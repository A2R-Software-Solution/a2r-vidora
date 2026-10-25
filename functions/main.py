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
from app.integration.groq_client import EmptyTranscriptionError
from app.pipeline.pipeline import PipelineError, run_pipeline
from app.pipeline.youtube_downloader import UnsupportedVideoError, VideoTooLongError
from app.services.credit_service import InsufficientCreditsError
from app.db.session import AsyncSessionLocal
from app.integration.embedding_client import embed_text

set_global_options(
    max_instances=settings.vidora_function_max_instances,
    memory=MemoryOption(settings.vidora_function_memory_mb),
    cpu=settings.vidora_function_cpu,
    timeout_sec=settings.vidora_function_timeout_seconds,
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
    concurrency=settings.vidora_function_concurrency,
    secrets=["GROQ_API_KEY", "GROQ_API_KEY_FALLBACK", "DATABASE_URL", "RECAPTCHA_SECRET_KEY",
             "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"],
)
def api(req: https_fn.Request) -> https_fn.Response:
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
    environ = dict(req.environ, PATH_INFO="/ping")
    return https_fn.Response.from_app(_wsgi_app, environ)


async def _process_video(data: dict) -> None:
    video_id = data.get("video_id")
    youtube_url = data.get("youtube_url")
    if not video_id or not youtube_url:
        raise ValueError("Task payload requires video_id and youtube_url.")

    async with AsyncSessionLocal() as db:
        await run_pipeline(uuid.UUID(video_id), youtube_url, db=db)


def _run_video_task(request) -> None:
    try:
        asyncio.run(_process_video(request.data))
    except PipelineError as exc:
        # Duration violations, missing credits and speechless videos are
        # permanent; retrying would repeat the same outcome (and could charge
        # again). Transient failures remain retryable.
        if isinstance(exc.__cause__, (VideoTooLongError, UnsupportedVideoError,
                                      InsufficientCreditsError, EmptyTranscriptionError)):
            return
        raise


@tasks_fn.on_task_dispatched(
    secrets=["GROQ_API_KEY", "GROQ_API_KEY_FALLBACK", "DATABASE_URL"],
    timeout_sec=settings.task_function_timeout_seconds,
    retry_config=RetryConfig(max_attempts=settings.task_max_attempts),
    rate_limits=RateLimits(max_concurrent_dispatches=settings.task_max_concurrent_dispatches),
)
def processvideo(request) -> None:
    _run_video_task(request)


# Same work for paid videos, on its own queue and concurrency so a backlog of
# free videos never delays them. Name must match VIDEO_PRIORITY_PROCESSING_TASK.
@tasks_fn.on_task_dispatched(
    secrets=["GROQ_API_KEY", "GROQ_API_KEY_FALLBACK", "DATABASE_URL"],
    timeout_sec=settings.task_function_timeout_seconds,
    retry_config=RetryConfig(max_attempts=settings.task_max_attempts),
    rate_limits=RateLimits(max_concurrent_dispatches=settings.task_priority_max_concurrent_dispatches),
)
def processvideopriority(request) -> None:
    _run_video_task(request)


@tasks_fn.on_task_dispatched(
    secrets=["DATABASE_URL"],
    timeout_sec=settings.shorts_timeout_seconds + 120,
    retry_config=RetryConfig(max_attempts=3),
    rate_limits=RateLimits(max_concurrent_dispatches=1),
)
def processshort(request) -> None:
    from app.pipeline.short_worker import process_short
    asyncio.run(process_short(request.data["short_id"], request.data["attempt_id"]))


@tasks_fn.on_task_dispatched(
    secrets=["DATABASE_URL"],
    timeout_sec=settings.audio_merge_timeout_seconds + 120,
    retry_config=RetryConfig(max_attempts=3),
    rate_limits=RateLimits(max_concurrent_dispatches=2),
)
def processaudiomerge(request) -> None:
    from app.pipeline.audio_merge_worker import process_audio_merge
    asyncio.run(process_audio_merge(request.data["merge_id"], request.data["attempt_id"]))


@scheduler_fn.on_schedule(
    schedule=settings.cleanup_schedule, secrets=["GROQ_API_KEY", "DATABASE_URL"]
)
def cleanup_expired_videos(event: scheduler_fn.ScheduledEvent) -> None:
    asyncio.run(run_cleanup())
