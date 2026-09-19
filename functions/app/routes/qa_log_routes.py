from app.controller.qa_log_controller import ask_question, list_qa_logs
from app.core.config import settings
from app.core.rate_limit import limiter
from app.utils.router_config import create_router

router = create_router(prefix="/videos/{video_id}/qa", tags=["QA"])

router.add_api_route(
    "/ask",
    limiter.limit(f"{settings.question_limit}/{settings.question_window_seconds} seconds")(ask_question),
    methods=["POST"],
)
router.add_api_route("", limiter.limit("50/minute")(list_qa_logs), methods=["GET"])
