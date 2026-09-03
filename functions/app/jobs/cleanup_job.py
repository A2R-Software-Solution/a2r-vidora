"""
app/jobs/cleanup_job.py

Deletes videos past their expires_at (and their transcript_chunks +
qa_logs). Opens its own DB session since this runs outside a request
context — invoked by a scheduled trigger (wired in main.py separately).
"""

from __future__ import annotations

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.services.video_service import VideoService


async def run_cleanup() -> int:
    async with AsyncSessionLocal() as db:
        service = VideoService(db)
        purged_count = await service.purge_expired()
        return purged_count


if __name__ == "__main__":
    import asyncio

    count = asyncio.run(run_cleanup())
    logger.info(f"Cleanup job finished: {count} videos purged")