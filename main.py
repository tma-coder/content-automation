import logging
from logging.handlers import RotatingFileHandler
import os
import config
import db
from scheduler.jobs import start_scheduler
import uvicorn


def setup_logging():
    os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(config.LOG_PATH, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)


def main():
    setup_logging()
    log = logging.getLogger(__name__)

    log.info("Initializing database...")
    db.init_db()

    log.info("Starting scheduler...")
    start_scheduler()

    log.info("=" * 50)
    log.info("  Dashboard: http://localhost:8080")
    log.info("=" * 50)

    from dashboard.app import app
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")


if __name__ == "__main__":
    main()
