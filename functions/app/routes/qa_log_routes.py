from app.controller.qa_log_controller import ask_question, list_qa_logs
from app.utils.router_config import create_router

router = create_router(prefix="/videos/{video_id}/qa", tags=["QA"])

router.add_api_route("/ask", ask_question, methods=["POST"])
router.add_api_route("", list_qa_logs, methods=["GET"])