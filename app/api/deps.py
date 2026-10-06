import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Workspace

logger = logging.getLogger("genpipe.api")

_redis = Redis.from_url(settings.redis_url, decode_responses=True)


def get_redis() -> Redis:
    return _redis


def get_workspace(
    session: Annotated[Session, Depends(get_session)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> Workspace:
    """Resolve the calling workspace from the X-API-Key header."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="missing API key")
    workspace = session.scalar(select(Workspace).where(Workspace.api_key == x_api_key))
    if workspace is None:
        logger.warning("rejected request with unknown API key %s", x_api_key)
        raise HTTPException(status_code=401, detail="invalid API key")
    return workspace


SessionDep = Annotated[Session, Depends(get_session)]
WorkspaceDep = Annotated[Workspace, Depends(get_workspace)]
RedisDep = Annotated[Redis, Depends(get_redis)]
