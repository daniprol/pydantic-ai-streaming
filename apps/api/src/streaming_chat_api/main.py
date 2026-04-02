from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from streaming_chat_api.config.settings import Settings, get_settings
from streaming_chat_api.routers.flows import router as flows_router
from streaming_chat_api.routers.health import router as health_router
from streaming_chat_api.services.runtime import build_lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    app = FastAPI(title=resolved_settings.app.name, lifespan=build_lifespan(resolved_settings))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['x-vercel-ai-ui-message-stream'],
    )

    app.include_router(health_router)
    app.include_router(flows_router)

    @app.get('/')
    async def root() -> dict[str, str]:
        return {'name': resolved_settings.app.name, 'status': 'ok'}

    return app


app = create_app()
