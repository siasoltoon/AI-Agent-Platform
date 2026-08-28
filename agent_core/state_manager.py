from enum import Enum

class AgentState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    FAILED = "failed"
    COMPLETED = "completed"
