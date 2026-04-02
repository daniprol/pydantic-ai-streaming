from __future__ import annotations

import json
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from streaming_chat_api.config.url_utils import normalize_local_service_url


API_DIR = Path(__file__).resolve().parents[3]
API_ENV_FILE = API_DIR / '.env'


class AppConfig(BaseModel):
    env: Literal['development', 'test', 'production']
    name: str
    host: str
    port: int
    cors_origins: list[str]

    @property
    def is_dev(self) -> bool:
        return self.env in ['development', 'test']


class DatabaseConfig(BaseModel):
    url: str
    echo: bool


class RedisConfig(BaseModel):
    url: str
    replay_stream_ttl_seconds: int


class TemporalConfig(BaseModel):
    target_host: str
    namespace: str
    task_queue: str


class DBOSConfigModel(BaseModel):
    system_database_url: str


class LLMConfig(BaseModel):
    azure_endpoint: str
    azure_api_key: str
    openai_api_version: str
    azure_model: str
    use_test_model: bool


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(API_ENV_FILE),
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

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

    dbos_system_database_url: str = 'postgresql://postgres:postgres@localhost:5432/streaming_chat'

    azure_openai_endpoint: str = Field(...)
    azure_openai_api_key: str = Field(...)
    openai_api_version: str = Field('2024-10-21')
    azure_openai_model: str = Field('gpt-5-mini')
    use_test_model: bool = False

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

    @field_validator('database_url', 'dbos_system_database_url', mode='after')
    @classmethod
    def normalize_database_hosts(cls, value: str) -> str:
        return normalize_local_service_url(value)

    @field_validator(
        'azure_openai_endpoint',
        'azure_openai_api_key',
        'openai_api_version',
        'azure_openai_model',
        mode='before',
    )
    @classmethod
    def strip_llm_string_fields(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator('azure_openai_endpoint', mode='after')
    @classmethod
    def validate_azure_openai_endpoint(cls, value: str) -> str:
        if not value:
            raise ValueError('azure_openai_endpoint must not be empty')
        if not value.startswith('https://'):
            raise ValueError('azure_openai_endpoint must start with https://')
        if 'openai.azure.com' not in value:
            raise ValueError('azure_openai_endpoint must be an Azure OpenAI endpoint')
        return value

    @field_validator('azure_openai_api_key', mode='after')
    @classmethod
    def validate_azure_openai_api_key(cls, value: str) -> str:
        if not value:
            raise ValueError('azure_openai_api_key must not be empty')
        return value

    @field_validator('openai_api_version', 'azure_openai_model', mode='after')
    @classmethod
    def validate_required_llm_strings(cls, value: str, info) -> str:
        if not value:
            raise ValueError(f'{info.field_name} must not be empty')
        return value

    @model_validator(mode='after')
    def validate_llm_configuration(self) -> Settings:
        if self.use_test_model:
            return self

        # Accessors run field validators and make startup fail with a clear settings error.
        self.azure_openai_endpoint
        self.openai_api_version
        self.azure_openai_model
        return self

    @cached_property
    def app(self) -> AppConfig:
        return AppConfig(
            env=self.app_env,
            name=self.app_name,
            host=self.app_host,
            port=self.app_port,
            cors_origins=self.app_cors_origins,
        )

    @cached_property
    def database(self) -> DatabaseConfig:
        return DatabaseConfig(url=self.database_url, echo=self.database_echo)

    @cached_property
    def redis(self) -> RedisConfig:
        return RedisConfig(
            url=self.redis_url,
            replay_stream_ttl_seconds=self.replay_stream_ttl_seconds,
        )

    @cached_property
    def temporal(self) -> TemporalConfig:
        return TemporalConfig(
            target_host=self.temporal_target_host,
            namespace=self.temporal_namespace,
            task_queue=self.temporal_task_queue,
        )

    @cached_property
    def dbos(self) -> DBOSConfigModel:
        return DBOSConfigModel(system_database_url=self.dbos_system_database_url)

    @cached_property
    def llm(self) -> LLMConfig:
        return LLMConfig(
            azure_endpoint=self.azure_openai_endpoint,
            azure_api_key=self.azure_openai_api_key,
            openai_api_version=self.openai_api_version,
            azure_model=self.azure_openai_model,
            use_test_model=self.use_test_model,
        )

    @property
    def llm_configured(self) -> bool:
        return not self.use_test_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
