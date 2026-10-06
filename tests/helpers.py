import json
import uuid
from datetime import datetime, timezone

from app.api.routes_webhooks import SIGNATURE_HEADER
from app.config import settings
from app.models import Workspace
from app.security import sign_payload


def auth(workspace: Workspace) -> dict:
    return {"X-API-Key": workspace.api_key}


def provider_event(generation_id: str, status: str, **extra) -> dict:
    event = {
        "event_id": f"evt_{uuid.uuid4().hex}",
        "generation_id": generation_id,
        "status": status,
        "output_urls": [],
        "error": None,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    event.update(extra)
    return event


def post_event(client, event: dict, signature: str | None = "valid"):
    """POST a provider event the way the provider does, signed by default."""
    body = json.dumps(event).encode()
    headers = {"Content-Type": "application/json"}
    if signature == "valid":
        headers[SIGNATURE_HEADER] = sign_payload(settings.provider_webhook_secret, body)
    elif signature is not None:
        headers[SIGNATURE_HEADER] = signature
    return client.post("/v1/webhooks/provider", content=body, headers=headers)
