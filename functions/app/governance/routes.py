"""Private Prometheus scrape endpoint; disabled unless a token is configured."""
import secrets
from fastapi import APIRouter, Header, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from app.core.config import settings

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics(authorization: str | None = Header(default=None)):
    token = settings.ai_metrics_token
    if not token:
        raise HTTPException(status_code=404, detail="Not found")
    if not secrets.compare_digest((authorization or "").encode(), ("Bearer " + token).encode()):
        raise HTTPException(status_code=401, detail="Invalid metrics credentials")
    return Response(content=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
