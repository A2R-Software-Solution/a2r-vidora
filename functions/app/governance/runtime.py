"""NIST AI RMF and ISO/IEC 42001 supporting controls; approval remains organizational."""
from functools import lru_cache, wraps
from pathlib import Path
from time import perf_counter
from typing import Literal
import asyncio
import json
import logging
import os
import uuid

from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import Counter, Histogram

from app.governance.aims import AIMSUnavailable, check_runtime

Operation = Literal["answer", "summary", "transcription", "embedding"]


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, str_strip_whitespace=True)
    version: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    approved: bool
    deployment_regions: list[str]
    evaluated_languages: list[str]
    operations: dict[Operation, str]


class GovernanceBlocked(Exception):
    """A deployment policy prevented an AI operation."""


@lru_cache
def get_policy() -> Policy:
    path = Path(os.environ.get("AI_POLICY_PATH", str(Path(__file__).with_name("policy.json"))))
    return Policy.model_validate_json(path.read_text())


CALLS = Counter("vidora_ai_calls_total", "AI operation outcomes", ["operation", "outcome"])
LATENCY = Histogram("vidora_ai_duration_seconds", "AI operation duration", ["operation"],
                    buckets=(.1, .5, 1, 2, 5, 10, 30, 60, 120))
QUALITY = Counter("vidora_ai_quality_events_total", "Observable quality signals, not correctness scores", ["signal"])
AUDIT = logging.getLogger("vidora.governance")


def enforce(policy: Policy, operation: Operation, model: str, *, production: bool,
            region: str, enabled: bool) -> None:
    if not enabled:
        raise GovernanceBlocked("AI processing is temporarily disabled.")
    if policy.operations.get(operation) != model:
        raise GovernanceBlocked("AI model is not approved by the deployment policy.")
    if production and (not policy.approved or policy.owner == "unassigned"
                       or not region or region not in policy.deployment_regions):
        raise GovernanceBlocked("AI deployment requires policy owner, approval, and an approved region.")


def governed(operation: Operation, model: str):
    """Gate before any model access; record bounded metadata only, including cancellation."""
    def decorate(fn):
        @wraps(fn)
        async def wrapped(*args, **kwargs):
            from app.core.config import settings
            started = perf_counter()
            outcome = "error"
            policy_version = "invalid"
            aims_digest = None
            try:
                try:
                    policy = get_policy()
                except (OSError, ValueError) as exc:
                    raise GovernanceBlocked("AI deployment policy is unavailable or invalid.") from exc
                policy_version = policy.version
                enforce(policy, operation, model, production=settings.is_production,
                        region=settings.ai_deployment_region,
                        enabled=settings.ai_enabled and os.environ.get("AI_EMERGENCY_STOP", "false").lower() != "true")
                if settings.is_production:
                    try:
                        aims_digest, blockers = check_runtime(policy,
                            release_id=settings.ai_release_id,
                            retention_hours=settings.video_retention_hours)
                    except AIMSUnavailable as exc:
                        raise GovernanceBlocked("AI management-system evidence is unavailable.") from exc
                    if blockers:
                        raise GovernanceBlocked("AI processing is unavailable pending management-system review.")
                result = await fn(*args, **kwargs)
                outcome = "success"
                return result
            except GovernanceBlocked:
                outcome = "blocked"
                raise
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            finally:
                elapsed = perf_counter() - started
                CALLS.labels(operation, outcome).inc()
                LATENCY.labels(operation).observe(elapsed)
                AUDIT.info(json.dumps({"event": "ai_operation", "event_id": str(uuid.uuid4()),
                    "policy_version": policy_version, "aims_sha256": aims_digest,
                    "operation": operation, "model": model,
                    "outcome": outcome, "duration_ms": round(elapsed * 1000)}))
        return wrapped
    return decorate
