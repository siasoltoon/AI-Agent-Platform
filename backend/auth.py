"""Authentication layer foundation."""

class AuthManager:
    def __init__(self):
        self.users = {}

    def register(self, user_id, data):
        self.users[user_id] = data

    def get_user(self, user_id):
        return self.users.get(user_id)
