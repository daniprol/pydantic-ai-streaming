from pathlib import Path

from streaming_chat_api.config.settings import API_ENV_FILE, Settings


def test_settings_load_api_env_file_location() -> None:
    assert API_ENV_FILE == Path(__file__).resolve().parents[2] / '.env'


def test_settings_support_test_model_flag() -> None:
    settings = Settings(use_test_model=True)
    assert settings.llm.use_test_model is True
    assert settings.llm_configured is False
