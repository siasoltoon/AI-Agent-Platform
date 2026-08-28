"""Tester agent foundation."""

class TesterAgent:
    name = "tester"

    def test(self, target):
        return {"status": "tested", "target": target}
