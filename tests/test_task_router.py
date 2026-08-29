import pytest

from task_engine.contracts import TaskRequest
from task_engine.registry import CommandRegistry
from task_engine.router import DEFAULT_COMMAND, TaskRouter


def test_registry_register_and_resolve():
    registry = CommandRegistry()

    def handler(task):
        return task.prompt

    registry.register(" demo.run ", handler)

    assert registry.has("demo.run")
    assert registry.resolve("DEMO.RUN") is handler
    assert registry.commands() == ("demo.run",)


def test_registry_rejects_duplicate_command_without_replace():
    registry = CommandRegistry()
    registry.register("demo.run", lambda task: task)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("demo.run", lambda task: task)


def test_router_uses_default_command():
    registry = CommandRegistry()
    calls = []

    def handler(task):
        calls.append(task.prompt)
        return {"ok": True}

    registry.register(DEFAULT_COMMAND, handler)
    router = TaskRouter(registry)
    task = TaskRequest(prompt="hello")

    assert router.route(task) == {"ok": True}
    assert calls == ["hello"]


def test_router_dispatches_metadata_command():
    registry = CommandRegistry()
    registry.register("custom.run", lambda task: task.prompt.upper())
    router = TaskRouter(registry)
    task = TaskRequest(prompt="hello", metadata={"command": " custom.run "})

    assert router.route(task) == "HELLO"


def test_router_rejects_unknown_command():
    router = TaskRouter()
    task = TaskRequest(prompt="hello", metadata={"command": "missing.command"})

    with pytest.raises(KeyError, match="Unknown command"):
        router.route(task)


def test_router_rejects_empty_command():
    registry = CommandRegistry()
    registry.register(DEFAULT_COMMAND, lambda task: task)
    router = TaskRouter(registry)
    task = TaskRequest(prompt="hello", metadata={"command": "   "})

    with pytest.raises(ValueError, match="cannot be empty"):
        router.route(task)
