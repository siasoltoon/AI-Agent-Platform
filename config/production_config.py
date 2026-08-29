"""Validated application configuration for production deployment."""

from __future__ import annotations

import os
from dataclasses import dataclass


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _cors_origins() -> tuple[str, ...]:
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5173,http://localhost:5173",
    )
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    if not origins:
        raise ValueError("CORS_ORIGINS must contain at least one origin.")
    if "*" in origins:
        raise ValueError("CORS_ORIGINS cannot contain '*' in production configuration.")

    # The local Vite dashboard uses port 5173. Keep these development origins
    # available even when an older local .env still contains only port 3000.
    if os.getenv("ENVIRONMENT", "development").strip().lower() != "production":
        for local_origin in ("http://127.0.0.1:5173", "http://localhost:5173"):
            if local_origin not in origins:
                origins.append(local_origin)
    return tuple(origins)


@dataclass(frozen=True)
class ProductionConfig:
    environment: str
    cors_origins: tuple[str, ...]
    host: str
    port: int
    log_level: str

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def load_config() -> ProductionConfig:
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    if environment not in {"development", "test", "production"}:
        raise ValueError("ENVIRONMENT must be development, test, or production.")

    host = os.getenv("API_HOST", "0.0.0.0").strip()
    if not host:
        raise ValueError("API_HOST cannot be empty.")

    log_level = os.getenv("LOG_LEVEL", "info").strip().lower()
    if log_level not in {"debug", "info", "warning", "error", "critical"}:
        raise ValueError("LOG_LEVEL must be debug, info, warning, error, or critical.")

    return ProductionConfig(
        environment=environment,
        cors_origins=_cors_origins(),
        host=host,
        port=_env_int("API_PORT", 8000, minimum=1, maximum=65535),
        log_level=log_level,
    )


CONFIG = load_config()
