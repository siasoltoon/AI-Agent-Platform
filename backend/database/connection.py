"""Database connection foundation."""

DATABASE_URL = "sqlite:///agent_platform.db"


def get_database_url():
    return DATABASE_URL
