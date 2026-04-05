from fastapi import APIRouter

from streaming_chat_api.routers import absurd, basic, dbos, dbos_replay, health, temporal


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(basic.router)
api_router.include_router(absurd.router)
api_router.include_router(dbos.router)
api_router.include_router(temporal.router)
api_router.include_router(dbos_replay.router)
