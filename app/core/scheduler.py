# from apscheduler.schedulers.background import BackgroundScheduler
# from tasks.pipeline import run_pipeline
# from core.config import SCRAPE_INTERVAL_MINUTES
# from core.logging import log

# scheduler = BackgroundScheduler()

# def start_scheduler():
#     log.info("scheduler_started")
#     scheduler.add_job(
#         run_pipeline,
#         "interval",
#         minutes=SCRAPE_INTERVAL_MINUTES,
#         max_instances=1,
#         coalesce=True
#     )
#     scheduler.start()

from apscheduler.schedulers.background import BackgroundScheduler
from tasks.pipeline import run_pipeline
from core.config import SCRAPE_INTERVAL_MINUTES
from core.logging import log

scheduler = BackgroundScheduler()
_scheduler_started = False

def start_scheduler():
    global _scheduler_started

    if _scheduler_started:
        log.info("scheduler_already_running")
        return

    log.info("scheduler_started")

    scheduler.add_job(
        run_pipeline,
        "interval",
        minutes=SCRAPE_INTERVAL_MINUTES,
        max_instances=1,
        coalesce=True,
        id="pipeline_job",
        replace_existing=True
    )

    scheduler.start()
    _scheduler_started = True