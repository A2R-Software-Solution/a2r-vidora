from app.controller.video_controller import list_videos, submit_video
from app.core.config import settings
from app.core.rate_limit import limiter
from app.utils.router_config import create_router

router = create_router(prefix="/videos", tags=["Videos"])

router.add_api_route(
    "/analyze",
    limiter.limit(f"{settings.submit_limit}/{settings.submit_window_seconds} seconds")(submit_video),
    methods=["POST"],
)
router.add_api_route("", limiter.limit("50/minute")(list_videos), methods=["GET"])
