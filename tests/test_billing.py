from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app import billing
from app.models import CreditTransaction, Job, TransactionKind
from app.worker import tasks


def test_charge_takes_cost_and_writes_ledger(session, workspace, make_job, balance_of):
    job = session.get(Job, make_job(workspace, num_outputs=3, cost=6))

    transaction = billing.charge_for_job(session, job)
    session.commit()

    assert transaction.kind == TransactionKind.CHARGE
    assert transaction.amount == -6
    assert balance_of(workspace) == 94


def test_charge_rejects_insufficient_balance(session, workspace, make_job, balance_of):
    job = session.get(Job, make_job(workspace, model="video-gen-1", num_outputs=2, cost=120))

    with pytest.raises(billing.InsufficientCredits) as excinfo:
        billing.charge_for_job(session, job)
    session.rollback()

    assert excinfo.value.required == 120
    assert balance_of(workspace) == 100


def test_refund_returns_credits_and_writes_ledger(session, workspace, make_job, balance_of):
    job = session.get(Job, make_job(workspace))
    billing.charge_for_job(session, job)
    billing.refund_for_job(session, job, reason="provider_failed")
    session.commit()

    assert balance_of(workspace) == 100
    kinds = session.scalars(
        select(CreditTransaction.kind).order_by(CreditTransaction.id)
    ).all()
    assert kinds == [TransactionKind.CHARGE, TransactionKind.REFUND]


def test_worker_charges_through_billing(workspace, make_job, monkeypatch):
    charge = MagicMock()
    monkeypatch.setattr(billing, "charge_for_job", charge)

    tasks.process_job.apply(args=[make_job(workspace)])

    charge.assert_called_once()
