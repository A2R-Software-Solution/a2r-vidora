import uuid

from fastapi import Depends, HTTPException, Query, Request, Response

from app.core.rate_limit import limiter
from app.deps import get_db, require_admin
from app.models.user_model import User
from app.schemas.admin_schema import CreditAdjustRequest, CreditAdjustResponse
from app.services.admin_service import AdminService
from app.utils.router_config import create_router

# Every route needs users.is_admin; a non-admin gets 403, a guest 401.
router = create_router(prefix="/admin", tags=["Admin"])
router.dependencies.append(Depends(require_admin))

Limit = Query(50, ge=1, le=200)
Offset = Query(0, ge=0, le=100_000)
Search = Query(None, max_length=100)


@router.get("/overview")
@limiter.limit("60/minute")
async def overview(request: Request, response: Response, db=Depends(get_db)):
    return await AdminService(db).overview()


@router.get("/users")
@limiter.limit("60/minute")
async def users(request: Request, response: Response, q: str | None = Search,
                limit: int = Limit, offset: int = Offset, db=Depends(get_db)):
    return await AdminService(db).users(q, limit, offset)


@router.get("/users/{user_id}")
@limiter.limit("60/minute")
async def user_detail(request: Request, response: Response, user_id: uuid.UUID, db=Depends(get_db)):
    detail = await AdminService(db).user_detail(user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return detail


@router.post("/users/{user_id}/credits", response_model=CreditAdjustResponse)
@limiter.limit("20/minute")
async def adjust_credits(request: Request, response: Response, user_id: uuid.UUID,
                         body: CreditAdjustRequest, db=Depends(get_db),
                         admin: User = Depends(require_admin)):
    balance = await AdminService(db).adjust_credits(user_id, body.amount, body.reason, admin.email)
    if balance is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return CreditAdjustResponse(user_id=user_id, purchased_balance=balance)


@router.get("/payments")
@limiter.limit("60/minute")
async def payments(request: Request, response: Response,
                   status: str | None = Query(None, pattern="^(created|paid|failed|refunded|disputed)$"),
                   limit: int = Limit, offset: int = Offset, db=Depends(get_db)):
    return await AdminService(db).payments(status, limit, offset)


@router.get("/videos")
@limiter.limit("60/minute")
async def videos(request: Request, response: Response,
                 status: str | None = Query(None, pattern="^(processing|completed|failed)$"),
                 q: str | None = Search, limit: int = Limit, offset: int = Offset, db=Depends(get_db)):
    return await AdminService(db).videos(status, q, limit, offset)


@router.get("/shorts")
@limiter.limit("60/minute")
async def shorts(request: Request, response: Response, status: str | None = Query(None, max_length=20),
                 limit: int = Limit, offset: int = Offset, db=Depends(get_db)):
    return await AdminService(db).shorts(status, limit, offset)


@router.get("/qa-logs")
@limiter.limit("60/minute")
async def qa_logs(request: Request, response: Response, q: str | None = Search,
                  limit: int = Limit, offset: int = Offset, db=Depends(get_db)):
    return await AdminService(db).qa_logs(q, limit, offset)
