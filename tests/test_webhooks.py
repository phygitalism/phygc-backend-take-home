import pytest

from app.models import JobStatus
from app.worker.tasks import process_job
from tests.helpers import post_event, provider_event


@pytest.fixture
def running_job(workspace, make_job, load_job):
    job_id = make_job(workspace)
    process_job.apply(args=[job_id])
    return load_job(job_id)


def test_succeeded_event_completes_job(client, running_job, load_job, workspace, balance_of):
    urls = ["https://cdn.acme-gen.example/gen_1/0.png"]
    event = provider_event(running_job.provider_generation_id, "succeeded", output_urls=urls)

    response = post_event(client, event)

    assert response.status_code == 200
    job = load_job(running_job.id)
    assert job.status == JobStatus.SUCCEEDED
    assert job.output_urls == urls
    assert balance_of(workspace) == 98


def test_failed_event_refunds_job(client, running_job, load_job, workspace, balance_of):
    event = provider_event(running_job.provider_generation_id, "failed", error="model_error")

    response = post_event(client, event)

    assert response.status_code == 200
    job = load_job(running_job.id)
    assert job.status == JobStatus.FAILED
    assert job.error == "model_error"
    assert balance_of(workspace) == 100


def test_processing_event_keeps_job_processing(client, running_job, load_job):
    event = provider_event(running_job.provider_generation_id, "processing")

    assert post_event(client, event).status_code == 200
    assert load_job(running_job.id).status == JobStatus.PROCESSING


def test_invalid_signature_is_rejected(client, running_job, load_job):
    event = provider_event(running_job.provider_generation_id, "succeeded")

    response = post_event(client, event, signature="sha256=deadbeef")

    assert response.status_code == 401
    assert load_job(running_job.id).status == JobStatus.PROCESSING


def test_unknown_generation(client):
    response = post_event(client, provider_event("gen_missing", "succeeded"))
    assert response.status_code == 404
