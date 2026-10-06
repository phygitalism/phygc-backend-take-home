from redis import Redis

WINDOW_SECONDS = 60


def allow_request(redis: Redis, workspace_id: int, limit: int) -> bool:
    """Fixed-window limiter: at most `limit` submissions per workspace per minute."""
    key = f"ratelimit:submit:{workspace_id}"
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, WINDOW_SECONDS)
    return count <= limit
