import pytest

from config.production_config import load_config


def test_production_config_reads_cors_origins_and_runtime_limits(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com, https://admin.example.com")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("API_PORT", "9000")
    monkeypatch.setenv("MAX_QUEUED_TASKS", "250")
    monkeypatch.setenv("SHUTDOWN_TIMEOUT_SECONDS", "20")

    config = load_config()

    assert config.is_production is True
    assert config.cors_origins == ("https://example.com", "https://admin.example.com")
    assert config.port == 9000
    assert config.max_queued_tasks == 250
    assert config.shutdown_timeout_seconds == 20.0


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


def test_production_config_rejects_invalid_runtime_limits(monkeypatch):
    monkeypatch.setenv("MAX_QUEUED_TASKS", "0")
    with pytest.raises(ValueError, match="MAX_QUEUED_TASKS"):
        load_config()

    monkeypatch.setenv("MAX_QUEUED_TASKS", "100")
    monkeypatch.setenv("SHUTDOWN_TIMEOUT_SECONDS", "121")
    with pytest.raises(ValueError, match="SHUTDOWN_TIMEOUT_SECONDS"):
        load_config()
