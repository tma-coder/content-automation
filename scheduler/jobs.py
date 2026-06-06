import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import config

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()
_auto_mode = config.AUTO_MODE


def is_auto_mode():
    return _auto_mode


def toggle_mode():
    global _auto_mode
    _auto_mode = not _auto_mode
    logger.info(f"Mode: {'AUTO' if _auto_mode else 'MANUAL'}")
    return _auto_mode


def _scheduled_cycle():
    from core.pipeline import run_cycle
    run_cycle(auto=_auto_mode)


def start_scheduler():
    scheduler.add_job(_scheduled_cycle, trigger=IntervalTrigger(minutes=config.POLL_INTERVAL_MINUTES),
                      id="news_cycle", replace_existing=True)
    scheduler.start()
    logger.info(f"Scheduler started ({config.POLL_INTERVAL_MINUTES} min interval)")
