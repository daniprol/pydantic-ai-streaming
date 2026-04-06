from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from streaming_chat_api.resources import build_lifespan
from streaming_chat_api.routers import api_router, health_router
from streaming_chat_api.settings import Settings, get_settings


def generate_operation_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else 'default'
    return f'{tag}-{route.name}'


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    app = FastAPI(
        title=resolved_settings.app_name,
        lifespan=build_lifespan(resolved_settings),
        openapi_url=f'{resolved_settings.api_v1_prefix}/openapi.json'
        if resolved_settings.is_dev
        else None,
        docs_url='/docs' if resolved_settings.is_dev else None,
        redoc_url='/redoc' if resolved_settings.is_dev else None,
        generate_unique_id_function=generate_operation_id,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'] if resolved_settings.is_dev else resolved_settings.app_cors_origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['x-replay-id', 'x-vercel-ai-ui-message-stream'],
    )

    app.include_router(health_router)
    app.include_router(api_router, prefix=resolved_settings.api_v1_prefix)

    @app.get('/')
    async def root() -> dict[str, str]:
        return {'name': resolved_settings.app_name, 'status': 'ok'}

    return app


app = create_app()
