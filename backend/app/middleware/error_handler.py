"""Global error handling foundation."""


def handle_exception(error: Exception) -> dict:
    return {
        "error": str(error),
        "type": error.__class__.__name__,
    }
