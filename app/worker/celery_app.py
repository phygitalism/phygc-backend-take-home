from celery import Celery

from app.config import settings

celery_app = Celery("genpipe", broker=settings.broker_url, include=["app.worker.tasks"])

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_ignore_result=True,
    # Do not lose jobs when a worker dies mid-task: the message goes back to the queue.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_always_eager=settings.celery_always_eager,
    task_eager_propagates=True,
    beat_schedule={
        "reap-stuck-jobs": {
            "task": "genpipe.reap_stuck_jobs",
            "schedule": 60.0,
        },
    },
)
