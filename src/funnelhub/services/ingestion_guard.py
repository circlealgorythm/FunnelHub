from __future__ import annotations

import secrets
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, status

from funnelhub.config import Settings

GETCOURSE_SECRET_HEADER = "x-funnelhub-webhook-secret"
GETCOURSE_SECRET_FIELD_NAMES = frozenset(
    {
        "secret",
        "webhook_secret",
        "fh_secret",
        "getcourse_webhook_secret",
    }
)


@dataclass
class InMemoryRateLimiter:
    buckets: dict[str, deque[float]] = field(default_factory=dict)

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int = 60,
        now: float | None = None,
        detail: str = "Too many requests.",
    ) -> None:
        if limit <= 0:
            return

        current = time.monotonic() if now is None else now
        cutoff = current - window_seconds
        bucket = self.buckets.setdefault(key, deque())
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
            )
        bucket.append(current)

        # Hardening 3.3: Prune stale buckets to avoid unbounded memory growth
        if len(self.buckets) > 500:
            stale_keys = [k for k, b in self.buckets.items() if not b or b[-1] <= cutoff]
            for k in stale_keys:
                del self.buckets[k]

    def reset(self) -> None:
        self.buckets.clear()


getcourse_rate_limiter = InMemoryRateLimiter()
auth_login_rate_limiter = InMemoryRateLimiter()


def enforce_login_rate_limit(
    *,
    request: Request,
    settings: Settings,
) -> None:
    client_ip = get_request_ip(request)
    auth_login_rate_limiter.check(
        f"login:{client_ip}",
        limit=settings.inbox_login_rate_limit_per_minute,
        detail="Too many login attempts. Please try again later.",
    )


def enforce_getcourse_ingestion_guard(
    *,
    request: Request,
    payload: Mapping[str, Any],
    settings: Settings,
    endpoint: str,
) -> None:
    client_ip = get_request_ip(request)
    getcourse_rate_limiter.check(
        f"{endpoint}:{client_ip}",
        limit=settings.getcourse_webhook_rate_limit_per_minute,
        detail="Too many GetCourse ingestion requests.",
    )
    validate_getcourse_webhook_secret(
        request=request,
        payload=payload,
        settings=settings,
    )


def validate_getcourse_webhook_secret(
    *,
    request: Request,
    payload: Mapping[str, Any],
    settings: Settings,
) -> None:
    configured_secret = clean_secret_value(settings.getcourse_webhook_secret)
    if configured_secret is None:
        return

    provided_secret = extract_getcourse_webhook_secret(request, payload)
    if provided_secret is None:
        if settings.getcourse_webhook_secret_required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="GetCourse webhook secret is required.",
            )
        return

    if not secrets.compare_digest(provided_secret, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid GetCourse webhook secret.",
        )


def extract_getcourse_webhook_secret(
    request: Request,
    payload: Mapping[str, Any],
) -> str | None:
    header_secret = clean_secret_value(request.headers.get(GETCOURSE_SECRET_HEADER))
    if header_secret is not None:
        return header_secret

    for key, value in payload.items():
        if is_getcourse_secret_field(key):
            payload_secret = clean_secret_value(value)
            if payload_secret is not None:
                return payload_secret
    return None


def strip_getcourse_webhook_secret_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in payload.items()
        if not is_getcourse_secret_field(key)
    }


def is_getcourse_secret_field(key: Any) -> bool:
    return str(key).strip().lower() in GETCOURSE_SECRET_FIELD_NAMES


def clean_secret_value(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def get_request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
        if ips:
            return ips[-1]
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"
