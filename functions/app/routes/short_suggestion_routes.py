from app.controller.short_suggestion_controller import suggest_shorts
from app.core.rate_limit import limiter
from app.utils.router_config import create_router

router = create_router(prefix="/videos/{video_id}/shorts", tags=["Shorts"])
router.add_api_route("/suggestions", limiter.limit("3/hour")(suggest_shorts), methods=["POST"])
