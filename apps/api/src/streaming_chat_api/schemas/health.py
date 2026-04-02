from __future__ import annotations

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    ok: bool
    detail: str


class HealthStatusResponse(BaseModel):
    uptime_seconds: float
    postgres: DependencyStatus
    redis: DependencyStatus
    temporal: DependencyStatus
    dbos: DependencyStatus
    llm: DependencyStatus
