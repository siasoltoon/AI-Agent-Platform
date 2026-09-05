"""Explicit network-access policy for agent terminal execution.

This policy can enforce command-level restrictions or request native network
containment. Native containment is implemented separately and fails closed
when the host cannot enforce it.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any


class NetworkPolicyError(PermissionError):
    """Raised when a terminal action violates the configured network policy."""


@dataclass(frozen=True)
class NetworkPolicy:
    """Control network access at the agent tool boundary."""

    mode: str = "restricted"

    _DIRECT_NETWORK_COMMANDS = frozenset({
        "curl", "wget", "fetch", "ftp", "sftp", "scp", "ssh", "telnet", "nc",
        "ncat", "netcat", "nmap", "nslookup", "dig", "ping", "tracert", "traceroute",
        "ipconfig", "ifconfig", "route", "arp", "netstat", "ss",
    })
    _PACKAGE_NETWORK_COMMANDS = frozenset({"pip", "pip3", "npm", "npm.cmd", "npx", "yarn", "pnpm", "cargo", "go"})
    _INTERPRETERS = frozenset({"python", "python3", "python.exe", "py", "node", "node.exe", "deno", "bun"})
    _NETWORK_MODULE_MARKERS = frozenset({
        "socket", "urllib", "http.client", "httpx", "requests", "aiohttp", "websocket",
        "ftplib", "paramiko", "telnetlib", "subprocess", "dns", "scapy",
    })
    _NETWORK_API_MARKERS = frozenset({
        "fetch(", "axios", "webrequest", "invoke-webrequest", "urlopen(", "create_connection(",
        "connect(", "requests.get(", "requests.post(", "http.get(", "http.request(",
    })

    def __post_init__(self) -> None:
        if self.mode not in {"deny", "restricted", "native", "allow"}:
            raise ValueError("Network policy mode must be deny, restricted, native, or allow.")

    def check_command(self, executable: str, command: str | None = None) -> None:
        name = str(executable).strip().lower()
        if self.mode in {"allow", "native"}:
            return
        if name in self._DIRECT_NETWORK_COMMANDS:
            raise NetworkPolicyError(f"Network command is blocked by policy: {name}")
        if self.mode == "deny" and name in self._PACKAGE_NETWORK_COMMANDS:
            raise NetworkPolicyError(f"Network-capable tool is blocked by policy: {name}")
        if name in self._INTERPRETERS and command:
            self._check_interpreter_command(name, command)

    @classmethod
    def _check_interpreter_command(cls, executable: str, command: str) -> None:
        """Reject obvious interpreter-level network escape attempts."""
        lowered = command.lower()
        try:
            tokens = [token.lower() for token in shlex.split(command, posix=True)]
        except ValueError as exc:
            raise NetworkPolicyError("Interpreter command contains invalid shell syntax.") from exc
        payload = " ".join(tokens[1:])
        if any(marker in payload for marker in cls._NETWORK_MODULE_MARKERS):
            raise NetworkPolicyError(f"Interpreter network access is blocked by policy: {executable}")
        if any(marker in lowered for marker in cls._NETWORK_API_MARKERS):
            raise NetworkPolicyError(f"Interpreter network API is blocked by policy: {executable}")

    def evidence(self, executable: str, *, allowed: bool) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "executable": str(executable).strip().lower(),
            "allowed": bool(allowed),
            "enforcement": "native-network-sandbox" if self.mode == "native" else "terminal-command-policy",
            "interpreter_escape_detection": self.mode not in {"allow", "native"},
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "enforcement": "native-network-sandbox" if self.mode == "native" else "terminal-command-policy",
            "interpreter_escape_detection": self.mode not in {"allow", "native"},
            "kernel_network_isolation": self.mode == "native",
        }
