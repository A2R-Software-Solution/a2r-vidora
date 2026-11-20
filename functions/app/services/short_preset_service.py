from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.short_model import ShortPreset

MAX_PRESETS = 10


class ShortPresetService:
    """A signed-in user's saved caption styles."""

    def __init__(self, db):
        self.db = db

    async def list(self, user_id):
        result = await self.db.execute(
            select(ShortPreset).where(ShortPreset.user_id == user_id).order_by(ShortPreset.created_at))
        return list(result.scalars())

    async def create(self, user_id, payload):
        count = (await self.db.execute(
            select(func.count()).select_from(ShortPreset).where(ShortPreset.user_id == user_id))).scalar_one()
        if count >= MAX_PRESETS:
            raise HTTPException(409, f"You can save up to {MAX_PRESETS} presets. Delete one first.")
        preset = ShortPreset(user_id=user_id, name=payload.name, style=payload.style.model_dump())
        self.db.add(preset)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(409, "You already have a preset with that name.") from None
        await self.db.refresh(preset)
        return preset

    async def delete(self, user_id, preset_id):
        preset = (await self.db.execute(
            select(ShortPreset).where(ShortPreset.id == preset_id, ShortPreset.user_id == user_id))).scalar_one_or_none()
        if preset is None:
            raise HTTPException(404, "Preset not found.")
        await self.db.delete(preset)
        await self.db.commit()
