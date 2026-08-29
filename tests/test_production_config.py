import pytest

from config.production_config import load_config


def test_production_config_reads_cors_origins(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com, https://admin.example.com")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("API_PORT", "9000")

    config = load_config()

    assert config.is_production is True
    assert config.cors_origins == ("https://example.com", "https://admin.example.com")
    assert config.port == 9000


def test_production_config_rejects_wildcard_cors(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(ValueError, match="cannot contain"):
        load_config()


def test_production_config_rejects_invalid_port(monkeypatch):
    monkeypatch.setenv("API_PORT", "70000")

    with pytest.raises(ValueError, match="between 1 and 65535"):
        load_config()


def test_production_config_rejects_invalid_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")

    with pytest.raises(ValueError, match="ENVIRONMENT"):
        load_config()
