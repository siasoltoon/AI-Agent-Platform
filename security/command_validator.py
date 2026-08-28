class CommandValidator:
    BLOCKED_COMMANDS = []

    def validate(self, command):
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command:
                return False
        return True
