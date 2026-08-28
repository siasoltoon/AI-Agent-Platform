"""Reviewer agent foundation."""

class ReviewerAgent:
    name = "reviewer"

    def review(self, result):
        return {"status": "reviewed", "result": result}
