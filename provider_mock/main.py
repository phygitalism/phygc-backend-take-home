"""Local simulator of the Acme Generative API.

This stands in for a third-party service. It is NOT part of the code under
review and you are not expected to change it. Its observable behaviour is
described in docs/provider_api.md; the MOCK_* variables below only tune how
often each documented behaviour shows up.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s provider-mock %(message)s")
logger = logging.getLogger("provider_mock")

API_KEY = os.getenv("MOCK_API_KEY", "dev-provider-key")
WEBHOOK_SECRET = os.getenv("MOCK_WEBHOOK_SECRET", "dev-webhook-secret")

RATE_429 = float(os.getenv("MOCK_RATE_429", "0.10"))
RATE_5XX = float(os.getenv("MOCK_RATE_5XX", "0.10"))
RATE_GENERATION_FAILS = float(os.getenv("MOCK_RATE_GENERATION_FAILS", "0.10"))
RATE_DUPLICATE_EVENT = float(os.getenv("MOCK_RATE_DUPLICATE_EVENT", "0.20"))
RATE_REORDERED_EVENTS = float(os.getenv("MOCK_RATE_REORDERED_EVENTS", "0.15"))
RATE_INSTANT = float(os.getenv("MOCK_RATE_INSTANT", "0.15"))
RATE_CANCEL_TOO_LATE = float(os.getenv("MOCK_RATE_CANCEL_TOO_LATE", "0.30"))
MIN_SECONDS = float(os.getenv("MOCK_MIN_SECONDS", "2"))
MAX_SECONDS = float(os.getenv("MOCK_MAX_SECONDS", "8"))

MODELS = ("flux-fast", "sdxl-pro", "upscale-4x", "video-gen-1")
TERMINAL = ("succeeded", "failed", "canceled")
WEBHOOK_RETRY_DELAYS = (1.0, 3.0, 10.0)

app = FastAPI(title="Acme Generative API (simulator)")

generations: dict[str, dict] = {}
idempotency_keys: dict[str, str] = {}
_background: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


class GenerationRequest(BaseModel):
    model: str
    prompt: str
    num_outputs: int = 1
    webhook_url: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_auth(authorization: str | None) -> None:
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid api key")


def _public(generation: dict) -> dict:
    return {
        "id": generation["id"],
        "model": generation["model"],
        "status": generation["status"],
        "output_urls": generation["output_urls"],
        "error": generation["error"],
        "created_at": generation["created_at"],
    }


def _event(generation: dict, status: str) -> dict:
    return {
        "event_id": f"evt_{uuid.uuid4().hex}",
        "generation_id": generation["id"],
        "status": status,
        "output_urls": generation["output_urls"] if status == "succeeded" else [],
        "error": generation["error"] if status == "failed" else None,
        "occurred_at": _now(),
    }


async def _deliver(webhook_url: str | None, event: dict) -> None:
    if not webhook_url:
        return
    body = json.dumps(event).encode()
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Provider-Signature": f"sha256={digest}",
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        for delay in (0.0, *WEBHOOK_RETRY_DELAYS):
            await asyncio.sleep(delay)
            try:
                response = await client.post(webhook_url, content=body, headers=headers)
            except httpx.HTTPError as exc:
                logger.info("webhook %s: transport error %r", event["event_id"], exc)
                continue
            logger.info(
                "webhook %s (%s) -> %s", event["event_id"], event["status"], response.status_code
            )
            if response.status_code < 500:
                # 2xx is success, 4xx is a permanent rejection: neither is retried.
                return
    logger.info("webhook %s: giving up", event["event_id"])


async def _send(webhook_url: str | None, event: dict) -> None:
    await _deliver(webhook_url, event)
    if random.random() < RATE_DUPLICATE_EVENT:
        await _deliver(webhook_url, event)


async def _run(generation_id: str) -> None:
    generation = generations[generation_id]
    webhook_url = generation["webhook_url"]
    instant = random.random() < RATE_INSTANT
    reordered = random.random() < RATE_REORDERED_EVENTS

    if not instant:
        await asyncio.sleep(random.uniform(0.2, 1.0))
    if generation["status"] == "canceled":
        return

    generation["status"] = "processing"
    processing_event = _event(generation, "processing")
    if not reordered:
        await _send(webhook_url, processing_event)

    if not instant:
        await asyncio.sleep(random.uniform(MIN_SECONDS, MAX_SECONDS))

    if generation["status"] == "canceled" and not generation["cancel_too_late"]:
        return

    if random.random() < RATE_GENERATION_FAILS:
        generation["status"] = "failed"
        generation["error"] = "model_error"
    else:
        generation["status"] = "succeeded"
        generation["output_urls"] = [
            f"https://cdn.acme-gen.example/{generation_id}/{i}.png"
            for i in range(generation["num_outputs"])
        ]
    await _send(webhook_url, _event(generation, generation["status"]))

    if reordered:
        await _send(webhook_url, processing_event)


@app.get("/v1/models")
async def list_models(authorization: Annotated[str | None, Header()] = None) -> dict:
    _check_auth(authorization)
    return {"models": [{"name": name, "available": True} for name in MODELS]}


@app.post("/v1/generations", status_code=202)
async def create_generation(
    request: GenerationRequest,
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    _check_auth(authorization)

    roll = random.random()
    if roll < RATE_429:
        return JSONResponse(
            status_code=429, content={"error": "rate_limited"}, headers={"Retry-After": "2"}
        )
    if roll < RATE_429 + RATE_5XX:
        return JSONResponse(status_code=503, content={"error": "temporarily_unavailable"})

    if request.model not in MODELS:
        return JSONResponse(status_code=422, content={"error": "unknown_model"})
    if "forbidden" in request.prompt.lower():
        return JSONResponse(status_code=400, content={"error": "content_policy_violation"})

    if idempotency_key and idempotency_key in idempotency_keys:
        return _public(generations[idempotency_keys[idempotency_key]])

    generation_id = f"gen_{uuid.uuid4().hex[:24]}"
    generations[generation_id] = {
        "id": generation_id,
        "model": request.model,
        "num_outputs": request.num_outputs,
        "webhook_url": request.webhook_url,
        "status": "queued",
        "output_urls": [],
        "error": None,
        "created_at": _now(),
        "cancel_too_late": False,
    }
    if idempotency_key:
        idempotency_keys[idempotency_key] = generation_id

    _spawn(_run(generation_id))
    return _public(generations[generation_id])


@app.get("/v1/generations/{generation_id}")
async def get_generation(
    generation_id: str, authorization: Annotated[str | None, Header()] = None
) -> dict:
    _check_auth(authorization)
    generation = generations.get(generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="generation not found")
    return _public(generation)


@app.post("/v1/generations/{generation_id}/cancel")
async def cancel_generation(
    generation_id: str, authorization: Annotated[str | None, Header()] = None
):
    _check_auth(authorization)
    generation = generations.get(generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="generation not found")
    if generation["status"] in TERMINAL:
        return JSONResponse(
            status_code=409,
            content={"error": "already_finished", "status": generation["status"]},
        )

    was_processing = generation["status"] == "processing"
    generation["status"] = "canceled"
    if was_processing and random.random() < RATE_CANCEL_TOO_LATE:
        # The model had already started; the generation will still complete.
        generation["cancel_too_late"] = True
    else:
        _spawn(_send(generation["webhook_url"], _event(generation, "canceled")))
    return _public(generation)
