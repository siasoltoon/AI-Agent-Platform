class PermissionManager:
    def __init__(self):
        self.permissions = {}

    def grant(self, agent, permission):
        self.permissions.setdefault(agent, set()).add(permission)

    def has_permission(self, agent, permission):
        return permission in self.permissions.get(agent, set())
