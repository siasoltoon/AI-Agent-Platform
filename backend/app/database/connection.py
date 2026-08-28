"""Database connection foundation."""

DATABASE_CONFIG = {
    "engine": "sqlite",
    "database": "agent_platform.db",
}


def get_database_config() -> dict:
    return DATABASE_CONFIG
