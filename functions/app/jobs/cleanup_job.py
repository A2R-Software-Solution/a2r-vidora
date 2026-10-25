"""
app/jobs/cleanup_job.py

Deletes videos past their expires_at (and their transcript_chunks +
qa_logs). Opens its own DB session since this runs outside a request
context — invoked by a scheduled trigger (wired in main.py separately).
"""

from __future__ import annotations

from datetime import timedelta

from app.core.config import settings
from app.middleware.logging import logger
from app.db.session import AsyncSessionLocal
from app.services.audio_merge_service import AudioMergeService
from app.services.credit_service import CreditService
from app.services.video_service import VideoService


async def run_cleanup() -> int:
    async with AsyncSessionLocal() as db:
        # Before purging, so a finished job is judged while its row still exists.
        finished = await CreditService(db).reconcile_held(
            older_than=timedelta(seconds=settings.stale_processing_seconds))
        logger.info("credit_holds_reconciled count=%s", finished)
        service = VideoService(db)
        purged_count = await service.purge_expired()
        await AudioMergeService(db).purge_expired()
        await db.commit()
        return purged_count


if __name__ == "__main__":
    import asyncio

    count = asyncio.run(run_cleanup())
    logger.info(f"Cleanup job finished: {count} videos purged")
