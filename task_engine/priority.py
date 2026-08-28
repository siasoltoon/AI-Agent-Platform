class TaskPriority:
    LEVELS = {
        "low": 1,
        "normal": 5,
        "high": 10,
        "critical": 20,
    }

    @classmethod
    def score(cls, level="normal"):
        return cls.LEVELS.get(level, cls.LEVELS["normal"])
