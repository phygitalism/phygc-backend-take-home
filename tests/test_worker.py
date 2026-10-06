from datetime import timedelta

from sqlalchemy import select, update

from app import billing
from app.models import CreditTransaction, Job, JobStatus, TransactionKind, utcnow
from app.provider.client import ProviderError
from app.worker.tasks import process_job, reap_stuck_jobs


def test_process_job_charges_and_starts_generation(
    workspace, make_job, provider, balance_of, load_job
):
    job_id = make_job(workspace)

    process_job.apply(args=[job_id])

    job = load_job(job_id)
    assert job.status == JobStatus.PROCESSING
    assert job.provider_generation_id == "gen_1"
    assert job.attempts == 1
    assert balance_of(workspace) == 98
    assert provider.calls[0]["webhook_url"].endswith("/v1/webhooks/provider")


def test_process_job_fails_and_refunds_when_provider_is_down(
    workspace, make_job, provider, balance_of, load_job, monkeypatch
):
    # No retries here, otherwise the test spends its time re-running the task.
    monkeypatch.setattr(process_job, "max_retries", 0)
    provider.error = ProviderError(503, "temporarily_unavailable")
    job_id = make_job(workspace)

    process_job.apply(args=[job_id])

    job = load_job(job_id)
    assert job.status == JobStatus.FAILED
    assert "503" in job.error
    assert balance_of(workspace) == 100


def test_process_job_without_credits(workspace, make_job, provider, balance_of, load_job):
    job_id = make_job(workspace, model="video-gen-1", num_outputs=2, cost=120)

    process_job.apply(args=[job_id])

    job = load_job(job_id)
    assert job.status == JobStatus.FAILED
    assert job.error == "insufficient_credits"
    assert balance_of(workspace) == 100
    assert provider.calls == []


def test_process_job_ignores_unknown_job(provider):
    process_job.apply(args=["00000000-0000-0000-0000-000000000000"])
    assert provider.calls == []


def test_reaper_fails_and_refunds_stuck_jobs(session, workspace, make_job, balance_of, load_job):
    stuck_id = make_job(workspace)
    fresh_id = make_job(workspace)
    for job_id in (stuck_id, fresh_id):
        job = session.get(Job, job_id)
        job.status = JobStatus.PROCESSING
        billing.charge_for_job(session, job)
    session.commit()
    session.execute(
        update(Job)
        .where(Job.id == stuck_id)
        .values(updated_at=utcnow() - timedelta(hours=1))
    )
    session.commit()

    reaped = reap_stuck_jobs.apply().get()

    assert reaped == 1
    assert load_job(stuck_id).status == JobStatus.FAILED
    assert load_job(stuck_id).error == "timeout"
    assert load_job(fresh_id).status == JobStatus.PROCESSING
    assert balance_of(workspace) == 98
    refunds = session.scalars(
        select(CreditTransaction).where(CreditTransaction.kind == TransactionKind.REFUND)
    ).all()
    assert [r.job_id for r in refunds] == [stuck_id]
