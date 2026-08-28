from datetime import datetime


def log_event(event, data=None):
    return {
        "time": datetime.utcnow().isoformat(),
        "event": event,
        "data": data,
    }
