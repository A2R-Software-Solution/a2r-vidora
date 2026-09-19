from fastapi import APIRouter
from app.controller.health_controller import health, ping
from app.core.rate_limit import limiter

router = APIRouter()

router.add_api_route("/health", limiter.limit("50/minute")(health), methods=["GET"])
router.add_api_route("/ping", limiter.limit("50/minute")(ping), methods=["GET"])
