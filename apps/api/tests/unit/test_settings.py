from pathlib import Path

import pytest
from pydantic import ValidationError

from streaming_chat_api.config.settings import API_ENV_FILE, Settings


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
    assert settings.llm.use_test_model is True
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
    ('app_env', 'expected'),
    [
        ('development', True),
        ('test', True),
        ('production', False),
    ],
)
def test_settings_app_config_is_dev(app_env: str, expected: bool) -> None:
    settings = build_settings(app_env=app_env)
    assert settings.app.is_dev is expected
