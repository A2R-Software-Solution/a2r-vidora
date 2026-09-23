"""Cloud Task dispatch for initial and quota-deferred video processing."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import uuid

from firebase_admin import functions as admin_functions

from app.core.config import settings


async def enqueue_video_processing(video_id: uuid.UUID, youtube_url: str, *,
                                   delay_seconds: float = 0) -> None:
    queue = admin_functions.task_queue(settings.video_processing_task)
    options = admin_functions.TaskOptions(
        dispatch_deadline_seconds=settings.task_function_timeout_seconds,
        task_id=(f"video-{video_id.hex}" if delay_seconds <= 0
                 else f"video-{video_id.hex}-resume-{uuid.uuid4().hex}"),
        **({"schedule_time": datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)}
           if delay_seconds > 0 else {}),
    )
    await asyncio.to_thread(
        queue.enqueue,
        {"data": {"video_id": str(video_id), "youtube_url": youtube_url}},
        options,
    )
