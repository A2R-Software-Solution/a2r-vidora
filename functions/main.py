import asyncio
import os

from asgiref.sync import async_to_sync
from firebase_admin import initialize_app, credentials
from firebase_functions import https_fn, scheduler_fn
from firebase_functions.options import MemoryOption, set_global_options


from app.core.config import settings
from app.jobs.cleanup_job import run_cleanup
from app.main import app as fastapi_app

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


@https_fn.on_request(secrets=["GROQ_API_KEY", "DATABASE_URL"])
def api(req: https_fn.Request) -> https_fn.Response:
    return https_fn.Response.from_app(_wsgi_app, req.environ)


@https_fn.on_request()
def ping(req: https_fn.Request) -> https_fn.Response:
    return https_fn.Response("pong", status=200)


@scheduler_fn.on_schedule(
    schedule="every 24 hours", secrets=["GROQ_API_KEY", "DATABASE_URL"]
)
def cleanup_expired_videos(event: scheduler_fn.ScheduledEvent) -> None:
    asyncio.run(run_cleanup())