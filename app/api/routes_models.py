import json

from fastapi import APIRouter

from app import catalog
from app.api.deps import RedisDep, WorkspaceDep
from app.config import settings
from app.provider.client import provider
from app.schemas import ModelOut

router = APIRouter(prefix="/v1/models", tags=["models"])

CACHE_KEY = "provider:models"


@router.get("", response_model=list[ModelOut])
async def list_models(workspace: WorkspaceDep, redis: RedisDep) -> list[ModelOut]:
    """Our catalog, with live availability from the provider."""
    cached = redis.get(CACHE_KEY)
    if cached:
        available = json.loads(cached)
    else:
        upstream = provider.list_models()
        available = {m["name"]: m["available"] for m in upstream["models"]}
        redis.set(CACHE_KEY, json.dumps(available), ex=settings.models_cache_ttl_seconds)

    return [
        ModelOut(
            name=spec.name,
            kind=spec.kind,
            price=spec.price,
            max_outputs=spec.max_outputs,
            available=available.get(spec.name, False),
        )
        for spec in catalog.MODELS.values()
    ]
