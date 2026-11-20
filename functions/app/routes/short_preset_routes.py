import uuid
from fastapi import Depends, HTTPException, Request, Response
from app.core.rate_limit import SIGN_IN_REQUIRED, limiter, rate_limit_user
from app.deps import get_db
from app.pipeline.short_catalog import BACKGROUNDS, FONTS, POSITIONS, PRESETS, RATIOS, SIZE_REFERENCE
from app.schemas.short_schema import (MAX_CAPTIONS, MAX_CAPTION_CHARS, ShortPresetRequest, ShortPresetResponse,
                                      ShortStyle)
from app.services.short_preset_service import MAX_PRESETS, ShortPresetService
from app.utils.router_config import create_router

router = create_router(prefix="/shorts", tags=["Shorts"])


def _signed_in(user_id):
    if user_id is None:
        raise HTTPException(401, SIGN_IN_REQUIRED)
    return user_id


@router.get("/options")
@limiter.limit("60/minute")
async def short_options(request: Request, response: Response, user_id=Depends(rate_limit_user)):
    """What the editor can offer: the server validates against the same lists."""
    return {
        "fonts": [{"key": key, "label": font["label"]} for key, font in FONTS.items()],
        "ratios": [{"key": key, "width": size[0], "height": size[1]} for key, size in RATIOS.items()],
        "backgrounds": list(BACKGROUNDS),
        "positions": list(POSITIONS),
        "presets": [{"key": key, "label": preset["label"], "style": ShortStyle(**preset["style"]).model_dump()}
                    for key, preset in PRESETS.items()],
        "defaults": ShortStyle().model_dump(),
        "limits": {"size": [24, 120], "outline_width": [0, 8], "max_captions": MAX_CAPTIONS,
                   "max_caption_chars": MAX_CAPTION_CHARS, "max_presets": MAX_PRESETS,
                   "size_reference": SIZE_REFERENCE},
    }


@router.get("/presets")
@limiter.limit("30/minute")
async def list_presets(request: Request, response: Response, db=Depends(get_db), user_id=Depends(rate_limit_user)):
    presets = await ShortPresetService(db).list(_signed_in(user_id))
    return [ShortPresetResponse.model_validate(preset) for preset in presets]


@router.post("/presets", response_model=ShortPresetResponse, status_code=201)
@limiter.limit("20/hour")
async def create_preset(payload: ShortPresetRequest, request: Request, response: Response,
                        db=Depends(get_db), user_id=Depends(rate_limit_user)):
    return await ShortPresetService(db).create(_signed_in(user_id), payload)


@router.delete("/presets/{preset_id}", status_code=204)
@limiter.limit("30/hour")
async def delete_preset(preset_id: uuid.UUID, request: Request, response: Response,
                        db=Depends(get_db), user_id=Depends(rate_limit_user)):
    await ShortPresetService(db).delete(_signed_in(user_id), preset_id)
    return Response(status_code=204)
