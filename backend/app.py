"""Backend application entry point."""

from .api_gateway import APIGateway

app = APIGateway()


def get_app():
    return app
