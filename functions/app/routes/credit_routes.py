from fastapi import Depends, Request, Response
from app.core.config import settings
from app.core.rate_limit import credit_owner_for, limiter, rate_limit_user
from app.deps import get_db
from app.schemas.credit_schema import CreditSummaryResponse
from app.services.credit_service import CreditService
from app.utils.router_config import create_router

router = create_router(prefix="/credits", tags=["Credits"])


@router.get("", response_model=CreditSummaryResponse)
@limiter.limit("50/minute")
async def get_credits(request: Request, response: Response, db=Depends(get_db),
                      user_id=Depends(rate_limit_user)):
    summary = await CreditService(db).summary(credit_owner_for(request, user_id))
    return CreditSummaryResponse(
        free_left=summary.free_left, free_daily=summary.free_daily,
        purchased_balance=summary.purchased_balance, available=summary.available,
        questions_left=summary.questions_left, is_paid=summary.is_paid,
        short_credit_cost=settings.short_credit_cost,
    )
