from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app import catalog
from app.api.deps import RedisDep, SessionDep, WorkspaceDep
from app.config import settings
from app.models import Job
from app.ratelimit import allow_request
from app.schemas import JobCreate, JobList, JobOut
from app.worker.tasks import process_job

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def job_to_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        model=job.model,
        prompt=job.prompt,
        num_outputs=job.num_outputs,
        status=job.status,
        cost=job.cost,
        charged=-sum(t.amount for t in job.transactions),
        output_urls=job.output_urls or [],
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("", status_code=202, response_model=JobOut)
def submit_job(
    payload: JobCreate, workspace: WorkspaceDep, session: SessionDep, redis: RedisDep
) -> JobOut:
    if not allow_request(redis, workspace.id, settings.submit_rate_limit_per_minute):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    spec = catalog.get_model(payload.model)
    if spec is None:
        raise HTTPException(status_code=422, detail=f"unknown model '{payload.model}'")
    if payload.num_outputs > spec.max_outputs:
        raise HTTPException(
            status_code=422,
            detail=f"{spec.name} supports at most {spec.max_outputs} outputs",
        )

    cost = catalog.job_cost(spec, payload.num_outputs)
    if workspace.credits < cost:
        raise HTTPException(status_code=402, detail="insufficient credits")

    job = Job(
        workspace_id=workspace.id,
        model=spec.name,
        prompt=payload.prompt,
        num_outputs=payload.num_outputs,
        cost=cost,
    )
    session.add(job)
    session.commit()

    process_job.delay(job.id)

    session.refresh(job)
    return job_to_out(job)


@router.get("", response_model=JobList)
def list_jobs(
    workspace: WorkspaceDep,
    session: SessionDep,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JobList:
    query = select(Job).where(Job.workspace_id == workspace.id)
    if status:
        query = query.where(Job.status == status)

    total = session.scalar(select(func.count()).select_from(query.subquery()))
    jobs = session.scalars(
        query.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return JobList(items=[job_to_out(job) for job in jobs], total=total)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, workspace: WorkspaceDep, session: SessionDep) -> JobOut:
    job = session.get(Job, job_id)
    if job is None or job.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="job not found")
    return job_to_out(job)
