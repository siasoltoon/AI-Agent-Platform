import os

import pytest

from agent_core.network_sandbox import NetworkSandbox, NetworkSandboxError


def test_command_policy_does_not_wrap_process():
    sandbox = NetworkSandbox("command-policy")
    assert sandbox.wrap(["python", "-c", "print(1)"]) == ["python", "-c", "print(1)"]
    assert sandbox.snapshot()["enforced"] is False


def test_none_does_not_wrap_process():
    assert NetworkSandbox("none").wrap(["pytest", "-q"]) == ["pytest", "-q"]


def test_native_wraps_on_hosts_with_unshare(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    sandbox = NetworkSandbox("native")
    monkeypatch.setattr(sandbox, "native_supported", True)
    assert sandbox.wrap(["python", "-c", "print(1)"]) == ["unshare", "--net", "--", "python", "-c", "print(1)"]
    assert sandbox.snapshot()["enforced"] is True


def test_native_fails_closed_when_unavailable(monkeypatch):
    sandbox = NetworkSandbox("native")
    monkeypatch.setattr(sandbox, "native_supported", False)
    with pytest.raises(NetworkSandboxError, match="Native network isolation is unavailable"):
        sandbox.wrap(["python", "-c", "print(1)"])


def test_fail_closed_mode_never_executes_without_native_support(monkeypatch):
    sandbox = NetworkSandbox("fail-closed")
    monkeypatch.setattr(sandbox, "native_supported", False)
    with pytest.raises(NetworkSandboxError):
        sandbox.wrap(["python", "-c", "print(1)"])
