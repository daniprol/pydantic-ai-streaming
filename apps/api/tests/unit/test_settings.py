from pathlib import Path

import pytest
from pydantic import ValidationError

from streaming_chat_api.settings import API_ENV_FILE, Settings


def build_settings(**overrides) -> Settings:
    values = {
        'azure_openai_endpoint': 'https://example-resource.openai.azure.com/',
        'azure_openai_api_key': 'test-key',
        'use_test_model': True,
        **overrides,
    }
    return Settings(**values)


def test_settings_load_api_env_file_location() -> None:
    assert API_ENV_FILE == Path(__file__).resolve().parents[2] / '.env'


def test_settings_support_test_model_flag() -> None:
    settings = build_settings()
    assert settings.use_test_model is True
    assert settings.llm_configured is False


def test_settings_require_non_empty_api_key_when_not_using_test_model() -> None:
    with pytest.raises(ValidationError, match='azure_openai_api_key'):
        build_settings(use_test_model=False, azure_openai_api_key='')


def test_settings_require_azure_endpoint_shape_when_not_using_test_model() -> None:
    with pytest.raises(ValidationError, match='azure_openai_endpoint'):
        build_settings(use_test_model=False, azure_openai_endpoint='http://localhost:1234')


def test_settings_accept_real_llm_configuration() -> None:
    settings = build_settings(use_test_model=False)
    assert settings.llm_configured is True


def test_settings_accept_direct_list_for_cors_origins() -> None:
    settings = build_settings(app_cors_origins=['http://localhost:5173', 'http://localhost:3000'])
    assert settings.app_cors_origins == ['http://localhost:5173', 'http://localhost:3000']


def test_settings_parse_single_env_cors_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('APP_CORS_ORIGINS', 'http://localhost:5173')
    settings = build_settings()
    assert settings.app_cors_origins == ['http://localhost:5173']


def test_settings_parse_comma_separated_env_cors_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('APP_CORS_ORIGINS', 'http://localhost:5173, http://localhost:3000')
    settings = build_settings()
    assert settings.app_cors_origins == ['http://localhost:5173', 'http://localhost:3000']


def test_settings_parse_json_env_cors_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('APP_CORS_ORIGINS', '["http://localhost:5173", "http://localhost:3000"]')
    settings = build_settings()
    assert settings.app_cors_origins == ['http://localhost:5173', 'http://localhost:3000']


def test_settings_reject_invalid_json_like_env_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('APP_CORS_ORIGINS', '[')
    with pytest.raises(ValidationError, match='app_cors_origins'):
        build_settings()


@pytest.mark.parametrize(
    ('app_env', 'expected'), [('development', True), ('test', True), ('production', False)]
)
def test_settings_is_dev_property(app_env: str, expected: bool) -> None:
    settings = build_settings(app_env=app_env)
    assert settings.is_dev is expected


def test_settings_normalize_local_postgres_host_for_local_execution() -> None:
    settings = build_settings(
        database_url='postgresql+asyncpg://postgres:postgres@postgres:5432/app'
    )
    assert '127.0.0.1' in settings.database_url


def test_settings_normalize_local_redis_host_for_local_execution() -> None:
    settings = build_settings(redis_url='redis://redis:6379/0')
    assert settings.redis_url == 'redis://127.0.0.1:6379/0'


def test_settings_normalize_local_temporal_host_for_local_execution() -> None:
    settings = build_settings(temporal_target_host='temporal:7233')
    assert settings.temporal_target_host == '127.0.0.1:7233'


def test_settings_require_temporal_target_host_port() -> None:
    with pytest.raises(ValidationError, match='temporal_target_host'):
        build_settings(temporal_target_host='localhost')


def test_settings_require_non_empty_temporal_namespace() -> None:
    with pytest.raises(ValidationError, match='temporal_namespace'):
        build_settings(temporal_namespace='   ')


def test_settings_require_positive_temporal_connect_attempts() -> None:
    with pytest.raises(ValidationError, match='temporal_connect_attempts'):
        build_settings(temporal_connect_attempts=0)


def test_settings_keep_container_hosts_when_running_in_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr('streaming_chat_api.settings.is_running_in_docker', lambda: True)
    settings = build_settings(
        redis_url='redis://redis:6379/0',
        temporal_target_host='temporal:7233',
    )
    assert settings.redis_url == 'redis://redis:6379/0'
    assert settings.temporal_target_host == 'temporal:7233'
