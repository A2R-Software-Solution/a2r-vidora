from app.controller.video_controller import list_videos, submit_video
from app.utils.router_config import create_router

router = create_router(prefix="/videos", tags=["Videos"])

router.add_api_route("/analyze", submit_video, methods=["POST"])
router.add_api_route("", list_videos, methods=["GET"])