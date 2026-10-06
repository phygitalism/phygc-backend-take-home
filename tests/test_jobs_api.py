from app.config import settings
from app.models import JobStatus
from tests.helpers import auth


def submit(client, workspace, **overrides):
    payload = {"model": "flux-fast", "prompt": "a lighthouse at dawn"}
    payload.update(overrides)
    return client.post("/v1/jobs", json=payload, headers=auth(workspace))


def test_requires_api_key(client):
    assert client.get("/v1/jobs").status_code == 401
    assert client.get("/v1/jobs", headers={"X-API-Key": "nope"}).status_code == 401


def test_submit_job_starts_generation(client, workspace, provider, balance_of):
    response = submit(client, workspace, num_outputs=2)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == JobStatus.PROCESSING
    assert body["cost"] == 4
    assert body["charged"] == 4
    assert balance_of(workspace) == 96
    assert provider.calls[0]["model"] == "flux-fast"
    assert provider.calls[0]["num_outputs"] == 2


def test_submit_unknown_model(client, workspace):
    response = submit(client, workspace, model="dall-e-9")
    assert response.status_code == 422


def test_submit_too_many_outputs(client, workspace):
    response = submit(client, workspace, model="upscale-4x", num_outputs=2)
    assert response.status_code == 422


def test_submit_without_credits(client, workspace, provider, balance_of):
    response = submit(client, workspace, model="video-gen-1", num_outputs=2)
    assert response.status_code == 202

    response = submit(client, workspace, model="video-gen-1", num_outputs=1)
    assert response.status_code == 402
    assert balance_of(workspace) == 20
    assert len(provider.calls) == 1


def test_submit_is_rate_limited(client, workspace, monkeypatch):
    monkeypatch.setattr(settings, "submit_rate_limit_per_minute", 2)
    assert submit(client, workspace).status_code == 202
    assert submit(client, workspace).status_code == 202
    assert submit(client, workspace).status_code == 429


def test_list_jobs_is_scoped_to_workspace(client, workspace, other_workspace):
    submit(client, workspace)
    submit(client, workspace)
    submit(client, other_workspace)

    body = client.get("/v1/jobs", headers=auth(workspace)).json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_jobs_filters_and_paginates(client, workspace):
    for _ in range(3):
        submit(client, workspace)

    page = client.get("/v1/jobs?limit=2&offset=2", headers=auth(workspace)).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1

    queued = client.get("/v1/jobs?status=queued", headers=auth(workspace)).json()
    assert queued["total"] == 0


def test_get_job(client, workspace, other_workspace):
    job_id = submit(client, workspace).json()["id"]

    assert client.get(f"/v1/jobs/{job_id}", headers=auth(workspace)).json()["id"] == job_id
    assert client.get(f"/v1/jobs/{job_id}", headers=auth(other_workspace)).status_code == 404
    assert client.get("/v1/jobs/does-not-exist", headers=auth(workspace)).status_code == 404
