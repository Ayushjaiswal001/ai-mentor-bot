"""Register recurring jobs on the PTB JobQueue."""

from telegram.ext import Application

from app.scheduler.jobs import heartbeat

HEARTBEAT_INTERVAL = 1800  # seconds (30 min) — fine-grained enough to catch any reminder hour


def register_jobs(app: Application) -> None:
    if app.job_queue is None:  # pragma: no cover - only if [job-queue] extra missing
        return
    app.job_queue.run_repeating(heartbeat, interval=HEARTBEAT_INTERVAL, first=20, name="heartbeat")
