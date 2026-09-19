from app.controller.user_controller import create_or_get_user, get_user
from app.core.rate_limit import limiter
from app.utils.router_config import create_router

router = create_router(prefix="/users", tags=["Users"])

router.add_api_route("", limiter.limit("10/minute")(create_or_get_user), methods=["POST"])
router.add_api_route("/{user_id}", limiter.limit("50/minute")(get_user), methods=["GET"])
