from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from streaming_chat_api.dependencies import ResourcesDep
from streaming_chat_api.schemas import DependencyStatus, HealthStatusResponse
from streaming_chat_api.resources import check_postgres, check_redis, check_temporal


router = APIRouter(prefix='/health', tags=['health'])


@router.get('/live')
async def live() -> dict[str, str]:
    return {'status': 'ok'}


@router.get('/ready')
async def ready(resources: ResourcesDep) -> dict[str, bool]:
    postgres_ok, _ = await check_postgres(resources)
    redis_ok, _ = await check_redis(resources)
    temporal_ok, _ = await check_temporal(resources)
    return {
        'ok': postgres_ok
        and redis_ok
        and temporal_ok
        and resources.dbos_initialized
        and resources.settings.llm_configured
    }


@router.get('/status', response_model=HealthStatusResponse)
async def status(resources: ResourcesDep) -> HealthStatusResponse:
    postgres_ok, postgres_detail = await check_postgres(resources)
    redis_ok, redis_detail = await check_redis(resources)
    temporal_ok, temporal_detail = await check_temporal(resources)
    now = datetime.now(timezone.utc)
    uptime_seconds = (now - resources.started_at).total_seconds()
    return HealthStatusResponse(
        uptime_seconds=uptime_seconds,
        postgres=DependencyStatus(ok=postgres_ok, detail=postgres_detail),
        redis=DependencyStatus(ok=redis_ok, detail=redis_detail),
        temporal=DependencyStatus(ok=temporal_ok, detail=temporal_detail),
        dbos=DependencyStatus(
            ok=resources.dbos_initialized,
            detail='initialized' if resources.dbos_initialized else 'not initialized',
        ),
        llm=DependencyStatus(
            ok=resources.settings.llm_configured,
            detail='azure-openai configured'
            if resources.settings.llm_configured
            else 'using pydantic-ai test model fallback',
        ),
    )
