"""Settings an admin can change from the admin panel without a deploy.

Overrides live in app_settings and are copied onto the shared `settings`
object, so every existing `settings.<name>` read sees them. Each instance
re-reads the table at most every REFRESH_SECONDS, so a change reaches all
instances within that time. A setting without a row keeps its .env value.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.middleware.logging import logger
from app.models.app_setting_model import AppSetting

REFRESH_SECONDS = 30


@dataclass(frozen=True)
class Editable:
    key: str
    group: str
    label: str
    minimum: int
    maximum: int
    unit: str = "credits"


FREE, QUESTIONS, COSTS, RETENTION, PACKS = (
    "Free credits per day", "Questions per day", "Feature costs", "Retention", "Credit packs")

EDITABLE: dict[str, Editable] = {e.key: e for e in (
    Editable("guest_daily_credits", FREE, "Guest (per device)", 0, 1000),
    Editable("user_daily_credits", FREE, "Signed-in user", 0, 1000),
    Editable("guest_ip_daily_credits", FREE, "All guests on one IP", 0, 5000),
    Editable("guest_daily_questions", QUESTIONS, "Guest (per device)", 0, 1000, "questions"),
    Editable("user_daily_questions", QUESTIONS, "Signed-in user", 0, 5000, "questions"),
    Editable("guest_ip_daily_questions", QUESTIONS, "All guests on one IP", 0, 5000, "questions"),
    Editable("paid_daily_questions", QUESTIONS, "User with purchased credits", 0, 100_000, "questions"),
    Editable("short_credit_cost", COSTS, "One Short", 1, 1000),
    Editable("audio_merge_extra_track_credits", COSTS, "Song Merger: each track after the first", 0, 100),
    Editable("video_retention_hours", RETENTION, "Video analysis", 1, 720, "hours"),
    Editable("shorts_retention_hours", RETENTION, "Shorts", 1, 720, "hours"),
    Editable("audio_merge_retention_hours", RETENTION, "Song Merger results", 1, 720, "hours"),
    Editable("media_download_retention_hours", RETENTION, "Downloads", 1, 720, "hours"),
    Editable("paid_retention_hours", RETENTION, "Everything, for users with purchased credits", 1, 2160, "hours"),
    Editable("pack_topup_credits", PACKS, "Top-up: credits", 1, 100_000),
    Editable("pack_topup_amount_cents", PACKS, "Top-up: price", 50, 100_000, "US cents"),
    Editable("pack_starter_credits", PACKS, "Starter: credits", 1, 100_000),
    Editable("pack_starter_amount_cents", PACKS, "Starter: price", 50, 100_000, "US cents"),
    Editable("pack_pro_credits", PACKS, "Pro: credits", 1, 100_000),
    Editable("pack_pro_amount_cents", PACKS, "Pro: price", 50, 100_000, "US cents"),
)}

# The .env values, captured before any override is applied.
DEFAULTS: dict[str, int] = {key: getattr(settings, key) for key in EDITABLE}

_loaded_at: float | None = None


class InvalidSettingError(ValueError):
    pass


def apply(overrides: dict[str, int]) -> None:
    """Sets every editable setting to its override, or back to its default.
    A stored value outside the allowed range is ignored."""
    for key, spec in EDITABLE.items():
        value = overrides.get(key)
        if value is None or not spec.minimum <= value <= spec.maximum:
            value = DEFAULTS[key]
        setattr(settings, key, value)


def validated(values: dict[str, int | None]) -> dict[str, int | None]:
    """None resets a setting to its default."""
    for key, value in values.items():
        spec = EDITABLE.get(key)
        if spec is None:
            raise InvalidSettingError(f"Unknown setting: {key}")
        if value is not None and not spec.minimum <= value <= spec.maximum:
            raise InvalidSettingError(
                f"{spec.group} / {spec.label} must be between {spec.minimum} and {spec.maximum}.")
    return values


async def refresh(*, force: bool = False) -> None:
    """Loads overrides if this instance's copy is older than REFRESH_SECONDS.
    A failed load is only logged: the values already in use stay."""
    global _loaded_at
    now = time.monotonic()
    if not force and _loaded_at is not None and now - _loaded_at < REFRESH_SECONDS:
        return
    _loaded_at = now  # also after a failure, so a broken table is not queried on every request
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(AppSetting.key, AppSetting.value))).all()
    except Exception:
        logger.exception("runtime_settings_refresh_failed")
        return
    apply({key: value for key, value in rows})


async def describe(db: AsyncSession) -> list[dict]:
    """Every editable setting with its current value, for the admin panel."""
    global _loaded_at
    rows = {row.key: row for row in (await db.execute(select(AppSetting))).scalars()}
    apply({key: row.value for key, row in rows.items()})
    _loaded_at = time.monotonic()
    return [{
        "key": key, "group": spec.group, "label": spec.label, "unit": spec.unit,
        "minimum": spec.minimum, "maximum": spec.maximum, "default": DEFAULTS[key],
        "value": getattr(settings, key), "overridden": key in rows,
        "updated_by": rows[key].updated_by if key in rows else None,
        "updated_at": rows[key].updated_at if key in rows else None,
    } for key, spec in EDITABLE.items()]


async def update(db: AsyncSession, values: dict[str, int | None], admin_email: str) -> list[dict]:
    """Saves overrides (None removes one) and applies them to this instance."""
    validated(values)
    now = datetime.now(timezone.utc)
    for key, value in values.items():
        if value is None:
            await db.execute(delete(AppSetting).where(AppSetting.key == key))
            continue
        row = {"value": value, "updated_by": admin_email, "updated_at": now}
        await db.execute(insert(AppSetting).values(key=key, **row)
                         .on_conflict_do_update(index_elements=[AppSetting.key], set_=row))
    await db.commit()
    logger.info("runtime_settings_updated admin=%s values=%s", admin_email, values)
    return await describe(db)
