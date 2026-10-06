from tests.helpers import auth


def submit(client, workspace):
    return client.post(
        "/v1/jobs",
        json={"model": "sdxl-pro", "prompt": "a lighthouse at dawn"},
        headers=auth(workspace),
    ).json()


def test_balance(client, workspace):
    submit(client, workspace)

    body = client.get("/v1/credits", headers=auth(workspace)).json()
    assert body == {"workspace": "Alpha", "credits": 95}


def test_transactions_are_scoped_to_workspace(client, workspace, other_workspace):
    submit(client, workspace)
    submit(client, other_workspace)
    submit(client, other_workspace)

    rows = client.get("/v1/credits/transactions", headers=auth(workspace)).json()
    assert len(rows) == 1
    assert rows[0]["kind"] == "charge"
    assert rows[0]["amount"] == -5


def test_transactions_for_one_job(client, workspace):
    first = submit(client, workspace)
    submit(client, workspace)

    rows = client.get(
        f"/v1/credits/transactions?job_id={first['id']}", headers=auth(workspace)
    ).json()
    assert [row["job_id"] for row in rows] == [first["id"]]


def test_models_merge_catalog_with_provider_availability(client, workspace, redis_client):
    models = client.get("/v1/models", headers=auth(workspace)).json()

    by_name = {m["name"]: m for m in models}
    assert by_name["flux-fast"]["available"] is True
    assert by_name["flux-fast"]["price"] == 2
    assert by_name["upscale-4x"]["available"] is False
    # Not reported by the provider at all
    assert by_name["video-gen-1"]["available"] is False
    assert redis_client.get("provider:models") is not None
