import uuid

from fastapi import Depends, HTTPException, Query, Request, Response

from app.core.rate_limit import limiter
from app.deps import get_db, require_admin
from app.models.user_model import User
from app.schemas.admin_schema import BanRequest, CreditAdjustRequest, CreditAdjustResponse, SettingsUpdateRequest
from app.services import runtime_settings
from app.services.admin_service import AdminBanError, AdminService
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


@router.get("/credits-summary")
@limiter.limit("30/minute")
async def credits_summary(request: Request, response: Response, db=Depends(get_db)):
    return await AdminService(db).credits_summary()


@router.get("/timeseries")
@limiter.limit("60/minute")
async def timeseries(request: Request, response: Response, days: int = Query(7, ge=7, le=90), db=Depends(get_db)):
    return await AdminService(db).timeseries(days)


@router.get("/activity")
@limiter.limit("60/minute")
async def activity(request: Request, response: Response, limit: int = Query(8, ge=1, le=30), db=Depends(get_db)):
    return await AdminService(db).activity(limit)


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


@router.post("/users/{user_id}/ban")
@limiter.limit("20/minute")
async def ban_user(request: Request, response: Response, user_id: uuid.UUID, body: BanRequest,
                   db=Depends(get_db), admin: User = Depends(require_admin)):
    try:
        found = await AdminService(db).ban(user_id, body.reason, admin)
    except AdminBanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not found:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user_id": user_id, "banned": True}


@router.post("/users/{user_id}/unban")
@limiter.limit("20/minute")
async def unban_user(request: Request, response: Response, user_id: uuid.UUID, db=Depends(get_db)):
    if not await AdminService(db).unban(user_id):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user_id": user_id, "banned": False}


@router.get("/settings")
@limiter.limit("60/minute")
async def get_settings(request: Request, response: Response, db=Depends(get_db)):
    return await runtime_settings.describe(db)


@router.put("/settings")
@limiter.limit("20/minute")
async def update_settings(request: Request, response: Response, body: SettingsUpdateRequest,
                          db=Depends(get_db), admin: User = Depends(require_admin)):
    try:
        return await runtime_settings.update(db, body.values, admin.email)
    except runtime_settings.InvalidSettingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
