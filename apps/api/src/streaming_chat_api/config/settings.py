from __future__ import annotations

from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


API_DIR = Path(__file__).resolve().parents[3]
API_ENV_FILE = API_DIR / '.env'


class AppConfig(BaseModel):
    env: Literal['development', 'test', 'production']
    name: str
    host: str
    port: int
    cors_origins: list[str]


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
    app_cors_origins: list[str] = Field(default_factory=lambda: ['http://localhost:5173'])

    database_url: str = 'sqlite+aiosqlite:///./streaming_chat.db'
    database_echo: bool = False

    redis_url: str = 'redis://localhost:6379/0'
    replay_stream_ttl_seconds: int = 3600

    temporal_target_host: str = 'localhost:7233'
    temporal_namespace: str = 'default'
    temporal_task_queue: str = 'streaming-chat'

    dbos_system_database_url: str = 'postgresql://postgres:postgres@localhost:5432/streaming_chat'

    azure_openai_endpoint: str = ''
    azure_openai_api_key: str = ''
    openai_api_version: str = '2024-10-21'
    azure_openai_model: str = 'gpt-4.1-mini'
    use_test_model: bool = False

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
        if self.use_test_model:
            return False
        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and 'replace-me' not in self.azure_openai_api_key
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
