import os
import pytest

from src.services import config


def test_data_dir_exists():
    assert config.DATA_DIR.exists()


def test_azure_openai_validation_raises_if_missing(monkeypatch):
    monkeypatch.setattr(config, "AZURE_OPENAI_ENDPOINT", None)
    monkeypatch.setattr(config, "AZURE_OPENAI_API_KEY", None)
    monkeypatch.setattr(config, "AZURE_OPENAI_API_VERSION", None)
    monkeypatch.setattr(config, "AZURE_OPENAI_DEPLOYMENT", None)

    with pytest.raises(EnvironmentError):
        config.validate_azure_openai_config()


def test_azure_search_validation_raises_if_missing(monkeypatch):
    monkeypatch.setattr(config, "AZURE_SEARCH_ENDPOINT", None)
    monkeypatch.setattr(config, "AZURE_SEARCH_KEY", None)
    monkeypatch.setattr(config, "AZURE_SEARCH_INDEX_NAME", None)

    with pytest.raises(EnvironmentError):
        config.validate_azure_search_config()