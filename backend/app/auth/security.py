"""Authentication foundation for AI Agent Platform."""

from datetime import datetime, timedelta


def create_access_token(subject: str, expires_minutes: int = 60) -> dict:
    return {
        "subject": subject,
        "expires_at": datetime.utcnow() + timedelta(minutes=expires_minutes),
    }


def verify_token(token: dict) -> bool:
    return bool(token.get("subject")) and token.get("expires_at") > datetime.utcnow()
