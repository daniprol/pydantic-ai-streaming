from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine.url import make_url

ThinkingLevel = Literal['none', 'minimal', 'low', 'medium', 'high', 'xhigh']


API_DIR = Path(__file__).resolve().parents[2]
API_ENV_FILE = API_DIR / '.env'
LOCAL_SERVICE_HOSTS = {
    'postgres': '127.0.0.1',
    'redis': '127.0.0.1',
    'temporal': '127.0.0.1',
}


def is_running_in_docker() -> bool:
    return Path('/.dockerenv').exists()


def normalize_local_service_url(url: str) -> str:
    if is_running_in_docker():
        return url

    parsed_url = make_url(url)
    local_host = LOCAL_SERVICE_HOSTS.get(parsed_url.host)
    if local_host is None:
        return url

    return parsed_url.set(host=local_host).render_as_string(hide_password=False)


def normalize_local_service_target(target: str) -> str:
    if is_running_in_docker():
        return target

    host, separator, remainder = target.partition(':')
    local_host = LOCAL_SERVICE_HOSTS.get(host)
    if local_host is None:
        return target

    if not separator:
        return local_host

    return f'{local_host}:{remainder}'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(API_ENV_FILE),
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    api_v1_prefix: str = '/api/v1'
    app_env: Literal['development', 'test', 'production'] = 'development'
    app_name: str = 'streaming-chat-api'
    app_host: str = '0.0.0.0'
    app_port: int = 8000
    app_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ['http://localhost:5173']
    )

    database_url: str = 'sqlite+aiosqlite:///./streaming_chat.db'
    database_echo: bool = False

    redis_url: str = 'redis://localhost:6379/0'
    replay_stream_ttl_seconds: int = 3600

    temporal_target_host: str = 'localhost:7233'
    temporal_namespace: str = 'default'
    temporal_task_queue: str = 'streaming-chat'
    temporal_connect_attempts: int = Field(default=10, ge=1)

    dbos_system_database_url: str = 'postgresql://postgres:postgres@localhost:5432/streaming_chat'

    azure_openai_endpoint: str = Field(default='https://example.openai.azure.com/')
    azure_openai_api_key: str = Field(default='test-key')
    openai_api_version: str = '2024-10-21'
    azure_openai_model: str = 'gpt-5-mini'
    thinking_level: ThinkingLevel = 'minimal'
    use_test_model: bool = False

    @property
    def is_dev(self) -> bool:
        return self.app_env in {'development', 'test'}

    @property
    def llm_configured(self) -> bool:
        return not self.use_test_model

    @field_validator('app_cors_origins', mode='before')
    @classmethod
    def validate_app_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, (list, tuple)):
            origins = list(value)
        elif isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return []

            if stripped_value.startswith('['):
                try:
                    origins = json.loads(stripped_value)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        'app_cors_origins must be a JSON array or a comma-separated string'
                    ) from exc
            else:
                origins = [item.strip() for item in stripped_value.split(',') if item.strip()]
        else:
            raise TypeError('app_cors_origins must be a list of strings or a string value')

        if not isinstance(origins, list) or any(not isinstance(item, str) for item in origins):
            raise ValueError('app_cors_origins must resolve to a list of strings')

        return origins

    @field_validator('database_url', 'dbos_system_database_url', 'redis_url', mode='after')
    @classmethod
    def normalize_database_hosts(cls, value: str) -> str:
        return normalize_local_service_url(value)

    @field_validator('temporal_target_host', mode='after')
    @classmethod
    def normalize_temporal_host(cls, value: str) -> str:
        return normalize_local_service_target(value)

    @field_validator('temporal_target_host', mode='after')
    @classmethod
    def validate_temporal_target_host(cls, value: str) -> str:
        host, separator, port = value.rpartition(':')
        if not separator or not host or not port:
            raise ValueError('temporal_target_host must be in host:port format')
        if not port.isdigit():
            raise ValueError('temporal_target_host port must be numeric')

        port_number = int(port)
        if port_number < 1 or port_number > 65535:
            raise ValueError('temporal_target_host port must be between 1 and 65535')

        return value

    @field_validator('temporal_namespace', 'temporal_task_queue', mode='after')
    @classmethod
    def validate_required_temporal_strings(cls, value: str) -> str:
        if not value:
            raise ValueError('value must not be empty')
        return value

    @field_validator(
        'temporal_target_host',
        'temporal_namespace',
        'temporal_task_queue',
        'azure_openai_endpoint',
        'azure_openai_api_key',
        'openai_api_version',
        'azure_openai_model',
        mode='before',
    )
    @classmethod
    def strip_string_fields(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode='after')
    def validate_llm_configuration(self) -> Settings:
        if self.use_test_model:
            return self

        if not self.azure_openai_endpoint.startswith('https://'):
            raise ValueError('azure_openai_endpoint must start with https://')
        if not self.azure_openai_api_key:
            raise ValueError('azure_openai_api_key must not be empty')
        if not self.openai_api_version:
            raise ValueError('openai_api_version must not be empty')
        if not self.azure_openai_model:
            raise ValueError('azure_openai_model must not be empty')
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
