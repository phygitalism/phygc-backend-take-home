import os

os.environ.setdefault(
    "GP_DATABASE_URL", "postgresql+psycopg://genpipe:genpipe@localhost:5432/genpipe_test"
)
os.environ["GP_CELERY_ALWAYS_EAGER"] = "1"

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api.deps import get_redis  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import Job, Workspace  # noqa: E402

if not settings.database_url.rsplit("/", 1)[-1].startswith("genpipe_test"):
    pytest.exit(
        "Refusing to run: the test suite drops and recreates all tables and must "
        "point at the genpipe_test database. Use `docker compose run --rm tests`.",
        returncode=2,
    )


class FakeProvider:
    """In-memory replacement for app.provider.client.provider."""

    def __init__(self):
        self.calls: list[dict] = []
        self.error: Exception | None = None

    def create_generation(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"id": f"gen_{len(self.calls)}", "status": "queued"}

    def list_models(self) -> dict:
        return {
            "models": [
                {"name": "flux-fast", "available": True},
                {"name": "sdxl-pro", "available": True},
                {"name": "upscale-4x", "available": False},
            ]
        }


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(_schema):
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE credit_transactions, jobs, workspaces RESTART IDENTITY CASCADE")
        )
    yield


@pytest.fixture
def session(_clean_tables):
    with SessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr("app.worker.tasks.provider", fake)
    monkeypatch.setattr("app.api.routes_models.provider", fake)
    return fake


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)


@pytest.fixture
def client(redis_client):
    app.dependency_overrides[get_redis] = lambda: redis_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def workspace(session):
    workspace = Workspace(name="Alpha", api_key="alpha-key", credits=100)
    session.add(workspace)
    session.commit()
    return workspace


@pytest.fixture
def other_workspace(session):
    workspace = Workspace(name="Beta", api_key="beta-key", credits=100)
    session.add(workspace)
    session.commit()
    return workspace


@pytest.fixture
def make_job(session):
    def _make_job(workspace: Workspace, **overrides) -> str:
        fields = {
            "workspace_id": workspace.id,
            "model": "flux-fast",
            "prompt": "a lighthouse at dawn",
            "num_outputs": 1,
            "cost": 2,
        }
        fields.update(overrides)
        job = Job(**fields)
        session.add(job)
        session.commit()
        return job.id

    return _make_job


@pytest.fixture
def balance_of(session):
    def _balance_of(workspace: Workspace) -> int:
        session.expire_all()
        return session.get(Workspace, workspace.id).credits

    return _balance_of


@pytest.fixture
def load_job(session):
    def _load_job(job_id: str) -> Job:
        session.expire_all()
        return session.get(Job, job_id)

    return _load_job
