class RollbackManager:
    def rollback(self, checkpoint=None):
        return {"success": True, "checkpoint": checkpoint}
