from datetime import datetime

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    model: str
    prompt: str = Field(min_length=1, max_length=2000)
    num_outputs: int = Field(default=1, ge=1)


class JobOut(BaseModel):
    id: str
    model: str
    prompt: str
    num_outputs: int
    status: str
    cost: int
    # Net credits currently taken for this job (charges minus refunds)
    charged: int
    output_urls: list[str]
    error: str | None
    created_at: datetime
    updated_at: datetime


class JobList(BaseModel):
    items: list[JobOut]
    total: int


class BalanceOut(BaseModel):
    workspace: str
    credits: int


class TransactionOut(BaseModel):
    id: int
    job_id: str | None
    kind: str
    amount: int
    note: str | None
    created_at: datetime


class ModelOut(BaseModel):
    name: str
    kind: str
    price: int
    max_outputs: int
    available: bool


class ProviderEvent(BaseModel):
    """Webhook payload sent by the provider, see docs/provider_api.md."""

    event_id: str
    generation_id: str
    status: str
    output_urls: list[str] = []
    error: str | None = None
    occurred_at: datetime
