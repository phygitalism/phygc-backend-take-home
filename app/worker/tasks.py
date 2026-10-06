import logging
from datetime import timedelta

from sqlalchemy import select

from app import billing
from app.config import settings
from app.db import SessionLocal
from app.models import Job, JobStatus, utcnow
from app.provider.client import ProviderError, provider
from app.worker.celery_app import celery_app

logger = logging.getLogger("genpipe.worker")

WEBHOOK_PATH = "/v1/webhooks/provider"


@celery_app.task(
    bind=True,
    name="genpipe.process_job",
    max_retries=settings.max_provider_attempts,
)
def process_job(self, job_id: str) -> None:
    """Charge the workspace and hand the job over to the provider.

    The provider works asynchronously: this task only starts the generation.
    The result arrives later through the webhook (app/api/routes_webhooks.py).
    """
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None:
            logger.warning("job %s not found, dropping", job_id)
            return

        job.status = JobStatus.PROCESSING
        job.attempts += 1

        # Charge up-front so we never generate for free.
        try:
            billing.charge_for_job(session, job)
        except billing.InsufficientCredits as exc:
            job.status = JobStatus.FAILED
            job.error = "insufficient_credits"
            session.commit()
            logger.info("job %s rejected: %s", job_id, exc)
            return
        session.commit()

        try:
            generation = provider.create_generation(
                model=job.model,
                prompt=job.prompt,
                num_outputs=job.num_outputs,
                webhook_url=f"{settings.public_base_url}{WEBHOOK_PATH}",
            )
        except ProviderError as exc:
            if self.request.retries >= self.max_retries:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                billing.refund_for_job(session, job, reason="provider_error")
                session.commit()
                logger.error("job %s failed after %s attempts", job_id, job.attempts)
                return
            logger.warning("job %s: provider error, retrying: %s", job_id, exc)
            raise self.retry(exc=exc, countdown=0)

        job.provider_generation_id = generation["id"]
        session.commit()
        logger.info("job %s started as generation %s", job_id, generation["id"])


@celery_app.task(name="genpipe.reap_stuck_jobs")
def reap_stuck_jobs() -> int:
    """Fail and refund jobs the provider never reported back on."""
    cutoff = utcnow() - timedelta(seconds=settings.job_timeout_seconds)
    with SessionLocal() as session:
        stuck = session.scalars(
            select(Job).where(
                Job.status == JobStatus.PROCESSING,
                Job.updated_at < cutoff,
            )
        ).all()
        for job in stuck:
            job.status = JobStatus.FAILED
            job.error = "timeout"
            billing.refund_for_job(session, job, reason="timeout")
            logger.warning("job %s timed out", job.id)
        session.commit()
        return len(stuck)
