from app.controller.user_controller import create_or_get_user, get_user
from app.utils.router_config import create_router

router = create_router(prefix="/users", tags=["Users"])

router.add_api_route("", create_or_get_user, methods=["POST"])
router.add_api_route("/{user_id}", get_user, methods=["GET"])