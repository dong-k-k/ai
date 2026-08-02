from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.api.forecast_service import ForecastService


LOGGER = logging.getLogger(__name__)
SEOUL = ZoneInfo("Asia/Seoul")


async def reload_forecasts_safely(service: ForecastService) -> None:
    try:
        await asyncio.to_thread(service.reload)
    except Exception:
        LOGGER.exception("03:00 forecast reload failed; keeping the previous snapshot")


def create_scheduler(service: ForecastService) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=SEOUL)
    scheduler.add_job(
        reload_forecasts_safely,
        trigger=CronTrigger(hour=3, minute=0, timezone=SEOUL),
        args=[service],
        id="daily_forecast_reload",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
