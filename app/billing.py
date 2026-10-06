"""Credit accounting.

Every balance change goes through this module and leaves a row in the
credit_transactions ledger. Callers own the transaction: nothing here commits.
"""

import logging

from sqlalchemy.orm import Session

from app import catalog
from app.models import CreditTransaction, Job, TransactionKind, Workspace

logger = logging.getLogger("genpipe.billing")


class InsufficientCredits(Exception):
    def __init__(self, workspace_id: int, balance: int, required: int):
        super().__init__(
            f"workspace {workspace_id} has {balance} credits, {required} required"
        )
        self.workspace_id = workspace_id
        self.balance = balance
        self.required = required


def _ensure_sufficient(workspace: Workspace, amount: int) -> None:
    if workspace.credits < amount:
        raise InsufficientCredits(workspace.id, workspace.credits, amount)


def charge_for_job(session: Session, job: Job) -> CreditTransaction:
    """Take the job's cost from the workspace balance."""
    workspace = session.get(Workspace, job.workspace_id)
    _ensure_sufficient(workspace, job.cost)

    workspace.credits = workspace.credits - job.cost
    transaction = CreditTransaction(
        workspace_id=workspace.id,
        job_id=job.id,
        kind=TransactionKind.CHARGE,
        amount=-job.cost,
    )
    session.add(transaction)
    session.flush()
    logger.info("charged %s credits for job %s", job.cost, job.id)
    return transaction


def refund_for_job(session: Session, job: Job, reason: str) -> CreditTransaction:
    """Give the credits for a job back to the workspace."""
    workspace = session.get(Workspace, job.workspace_id)
    spec = catalog.get_model(job.model)
    amount = spec.price

    workspace.credits = workspace.credits + amount
    transaction = CreditTransaction(
        workspace_id=workspace.id,
        job_id=job.id,
        kind=TransactionKind.REFUND,
        amount=amount,
        note=reason,
    )
    session.add(transaction)
    session.flush()
    logger.info("refunded %s credits for job %s (%s)", amount, job.id, reason)
    return transaction


def top_up(session: Session, workspace: Workspace, amount: int, note: str | None = None) -> None:
    workspace.credits = workspace.credits + amount
    session.add(
        CreditTransaction(
            workspace_id=workspace.id,
            kind=TransactionKind.TOPUP,
            amount=amount,
            note=note,
        )
    )
    session.flush()
