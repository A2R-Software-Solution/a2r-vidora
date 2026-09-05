from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.governance.routes import router as governance_router
from app.governance.runtime import GovernanceBlocked
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(video_router)
app.include_router(qa_log_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(governance_router)


@app.exception_handler(GovernanceBlocked)
async def governance_blocked_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})
