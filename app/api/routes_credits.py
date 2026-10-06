from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import SessionDep, WorkspaceDep
from app.models import CreditTransaction
from app.schemas import BalanceOut, TransactionOut

router = APIRouter(prefix="/v1/credits", tags=["credits"])


@router.get("", response_model=BalanceOut)
def get_balance(workspace: WorkspaceDep) -> BalanceOut:
    return BalanceOut(workspace=workspace.name, credits=workspace.credits)


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    workspace: WorkspaceDep,
    session: SessionDep,
    job_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TransactionOut]:
    """Ledger for the workspace, or for a single job when job_id is given."""
    query = select(CreditTransaction)
    if job_id:
        query = query.where(CreditTransaction.job_id == job_id)
    else:
        query = query.where(CreditTransaction.workspace_id == workspace.id)

    rows = session.scalars(
        query.order_by(CreditTransaction.id.desc()).limit(limit).offset(offset)
    ).all()
    return [
        TransactionOut(
            id=row.id,
            job_id=row.job_id,
            kind=row.kind,
            amount=row.amount,
            note=row.note,
            created_at=row.created_at,
        )
        for row in rows
    ]
