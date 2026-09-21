"""
Redis integration — spec §15.

Used for: (1) short-lived per-task event streams that Phase 6's SSE/
WebSocket endpoint will read from, and (2) a small repository-memory cache
(detected test framework, etc.) so repeat tasks against the same repo
don't redo cheap-but-repeated detection work. Redis is explicitly NOT the
source of truth for task history — that's PostgreSQL (task_repository.py).
"""
from __future__ import annotations

import json
import time

import redis

from app.config import get_settings

_client: redis.Redis | None = None

_EVENT_TTL_SECONDS = 3600           # per-task event stream expires after an hour
_REPO_MEMORY_TTL_SECONDS = 3600     # repository memory cache TTL


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def publish_event(task_id: str, event_type: str, data: dict | None = None) -> None:
    """
    Append a structured event to this task's stream. Matches the event
    vocabulary from spec §13 (agent_started, agent_completed, ...) so the
    SSE endpoint (api/routes.py: stream_task_events) can tail this list
    directly with no format translation needed. Stored as a Redis LIST
    (not pub/sub) specifically so a client that connects at any point
    - before, during, or after the run - can never miss an event: list
    entries persist regardless of when a reader shows up, unlike a
    broadcast that only reaches subscribers active at publish time.
    """
    client = get_redis_client()
    key = f"task_events:{task_id}"
    payload = json.dumps({"type": event_type, "timestamp": time.time(), **(data or {})})
    try:
        client.rpush(key, payload)
        client.expire(key, _EVENT_TTL_SECONDS)
    except redis.RedisError:
        # Event streaming is a nice-to-have, not a correctness requirement —
        # a Redis outage must never fail the underlying agent task.
        pass


def get_events(task_id: str) -> list[dict]:
    client = get_redis_client()
    try:
        raw = client.lrange(f"task_events:{task_id}", 0, -1)
        return [json.loads(item) for item in raw]
    except redis.RedisError:
        return []


def cache_repository_memory(repo_key: str, memory: dict) -> None:
    client = get_redis_client()
    try:
        client.set(f"repo_memory:{repo_key}", json.dumps(memory), ex=_REPO_MEMORY_TTL_SECONDS)
    except redis.RedisError:
        pass


def get_repository_memory(repo_key: str) -> dict | None:
    client = get_redis_client()
    try:
        raw = client.get(f"repo_memory:{repo_key}")
        return json.loads(raw) if raw else None
    except redis.RedisError:
        return None


def tail_events(task_id: str, start_index: int, is_still_running,
                 poll_interval_seconds: float = 0.15, max_wait_seconds: float = 120.0):
    """
    Yield events for this task from `start_index` onward, polling the
    durable Redis list rather than subscribing to pub/sub. A pub/sub
    subscription can miss a message published in the gap between checking
    "is this task still running" and actually subscribing; a list has no
    such race - every publish() is a persisted RPUSH, so a poll can never
    miss one, it just might see it slightly later.

    `is_still_running` is a zero-arg callable (not a snapshot) checked each
    poll cycle: once it returns False AND a poll finds nothing new, we stop
    promptly instead of waiting out max_wait_seconds. max_wait_seconds is
    then just a backstop against a genuinely stuck/crashed run.
    """
    import time as _time
    client = get_redis_client()
    key = f"task_events:{task_id}"
    index = start_index
    elapsed = 0.0
    while elapsed < max_wait_seconds:
        try:
            raw = client.lrange(key, index, -1)
        except redis.RedisError:
            raw = []
        for item in raw:
            event = json.loads(item)
            index += 1
            yield event
            if event.get("type") in ("task_paused_or_completed", "task_error"):
                return
        if not raw and not is_still_running():
            return
        _time.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds
