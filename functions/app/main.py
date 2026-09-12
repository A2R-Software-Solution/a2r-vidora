from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.routes.user_routes import router as user_router
from app.routes.video_routes import router as video_router
from app.routes.qa_log_routes import router as qa_log_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting {settings.app_name} ({settings.environment})")
    yield
    logger.info("Shutting down")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://a2r-vidora.vercel.app",
        "https://vidoraa.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(video_router)
app.include_router(qa_log_router)


@app.exception_handler(Exception)
async def report_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Emit one safe, searchable event for unexpected API failures.

    Cloud Monitoring alerts on this event and on 5xx request logs.  Do not log
    request bodies here: video URLs, credentials and other user input must not
    be copied into operational alert emails.
    """
    logger.exception(
        "unhandled_request_error method=%s path=%s error_type=%s",
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred."},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
