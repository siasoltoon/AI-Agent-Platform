"""
Worker Client

Communicates with Remote/Local AI Worker.
"""

import requests


class WorkerClient:

    def __init__(
        self,
        host: str,
        port: int
    ):

        self.base_url = (
            f"http://{host}:{port}"
        )


    def health_check(self):

        response = requests.get(
            f"{self.base_url}/health",
            timeout=10
        )

        response.raise_for_status()

        return response.json()



    def execute_task(
        self,
        task: dict
    ):

        response = requests.post(
            f"{self.base_url}/execute",
            json=task,
            timeout=300
        )

        response.raise_for_status()

        return response.json()
