import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app import billing
from app.api.deps import SessionDep
from app.config import settings
from app.models import Job, JobStatus
from app.schemas import ProviderEvent
from app.security import verify_signature

logger = logging.getLogger("genpipe.webhooks")

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

SIGNATURE_HEADER = "X-Provider-Signature"


@router.post("/provider")
async def provider_webhook(request: Request, session: SessionDep) -> dict:
    """Receive generation status updates from the provider."""
    # The signature is computed over the raw body, so read it before parsing.
    raw_body = await request.body()

    signature = request.headers.get(SIGNATURE_HEADER)
    if signature and not verify_signature(
        settings.provider_webhook_secret, raw_body, signature
    ):
        raise HTTPException(status_code=401, detail="invalid signature")

    event = ProviderEvent.model_validate_json(raw_body)
    logger.info(
        "webhook %s: generation %s is %s", event.event_id, event.generation_id, event.status
    )

    job = session.scalar(
        select(Job).where(Job.provider_generation_id == event.generation_id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="unknown generation")

    if event.status == "succeeded":
        job.status = JobStatus.SUCCEEDED
        job.output_urls = event.output_urls
        job.error = None
    elif event.status == "failed":
        job.status = JobStatus.FAILED
        job.error = event.error or "provider_failed"
        billing.refund_for_job(session, job, reason="provider_failed")
    elif event.status == "processing":
        job.status = JobStatus.PROCESSING

    session.commit()
    return {"ok": True}
