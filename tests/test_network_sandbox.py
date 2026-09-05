import subprocess

import pytest

from agent_core import network_sandbox
from agent_core.network_sandbox import NetworkSandbox, NetworkSandboxError


def test_command_policy_does_not_wrap_process():
    sandbox = NetworkSandbox("command-policy")
    assert sandbox.wrap(["python", "-c", "print(1)"]) == ["python", "-c", "print(1)"]
    assert sandbox.snapshot()["enforced"] is False


def test_none_does_not_wrap_process():
    assert NetworkSandbox("none").wrap(["pytest", "-q"]) == ["pytest", "-q"]


def test_native_wraps_when_preflight_succeeds(monkeypatch):
    monkeypatch.setattr(network_sandbox.os, "name", "posix")
    monkeypatch.setattr(network_sandbox.shutil, "which", lambda command: "/usr/bin/unshare" if command == "unshare" else None)
    monkeypatch.setattr(network_sandbox.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, b"", b""))
    sandbox = NetworkSandbox("native")
    assert sandbox.native_supported is True
    assert sandbox.preflight()["available"] is True
    assert sandbox.wrap(["python", "-c", "print(1)"]) == ["unshare", "--net", "--", "python", "-c", "print(1)"]
    assert sandbox.snapshot()["enforced"] is True
    assert sandbox.snapshot()["native_available"] is True


def test_native_fails_closed_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(network_sandbox.os, "name", "posix")
    monkeypatch.setattr(network_sandbox.shutil, "which", lambda command: "/usr/bin/unshare" if command == "unshare" else None)
    monkeypatch.setattr(network_sandbox.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, b"", b"Operation not permitted"))
    sandbox = NetworkSandbox("native")
    assert sandbox.native_supported is True
    assert sandbox.preflight()["available"] is False
    with pytest.raises(NetworkSandboxError, match="Operation not permitted"):
        sandbox.wrap(["python", "-c", "print(1)"])
    assert sandbox.snapshot()["enforced"] is False
    assert sandbox.snapshot()["native_available"] is False


def test_native_fails_closed_when_unavailable(monkeypatch):
    monkeypatch.setattr(network_sandbox.os, "name", "posix")
    monkeypatch.setattr(network_sandbox.shutil, "which", lambda command: None)
    sandbox = NetworkSandbox("native")
    with pytest.raises(NetworkSandboxError, match="unshare is unavailable"):
        sandbox.wrap(["python", "-c", "print(1)"])


def test_fail_closed_mode_never_executes_without_native_support(monkeypatch):
    monkeypatch.setattr(network_sandbox.os, "name", "posix")
    monkeypatch.setattr(network_sandbox.shutil, "which", lambda command: None)
    sandbox = NetworkSandbox("fail-closed")
    with pytest.raises(NetworkSandboxError):
        sandbox.wrap(["python", "-c", "print(1)"])
