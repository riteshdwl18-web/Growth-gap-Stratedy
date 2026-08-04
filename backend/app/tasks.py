from __future__ import annotations

from app.celery_app import celery_app
from app.services.screener import execute_run_task


@celery_app.task(name="app.tasks.process_run_task")
def process_run_task(run_id: str) -> None:
    execute_run_task(run_id)
