"""Explicit network-access policy for agent terminal execution.

This is a command/tool policy, not a kernel network namespace or firewall. It
fails closed for explicitly network-oriented terminal programs while preserving
common local development toolchains in restricted mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class NetworkPolicyError(PermissionError):
    """Raised when a terminal action violates the configured network policy."""


@dataclass(frozen=True)
class NetworkPolicy:
    """Control network-oriented terminal commands at the agent tool boundary."""

    mode: str = "restricted"

    _DIRECT_NETWORK_COMMANDS = frozenset({
        "curl", "wget", "fetch", "ftp", "sftp", "scp", "ssh", "telnet", "nc",
        "ncat", "netcat", "nmap", "nslookup", "dig", "ping", "tracert", "traceroute",
        "ipconfig", "ifconfig", "route", "arp", "netstat", "ss",
    })
    _PACKAGE_NETWORK_COMMANDS = frozenset({"pip", "pip3", "npm", "npm.cmd", "npx", "yarn", "pnpm", "cargo", "go"})

    def __post_init__(self) -> None:
        if self.mode not in {"deny", "restricted", "allow"}:
            raise ValueError("Network policy mode must be deny, restricted, or allow.")

    def check_command(self, executable: str) -> None:
        name = str(executable).strip().lower()
        if self.mode == "allow":
            return
        if name in self._DIRECT_NETWORK_COMMANDS:
            raise NetworkPolicyError(f"Network command is blocked by policy: {name}")
        if self.mode == "deny" and name in self._PACKAGE_NETWORK_COMMANDS:
            raise NetworkPolicyError(f"Network-capable tool is blocked by policy: {name}")

    def evidence(self, executable: str, *, allowed: bool) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "executable": str(executable).strip().lower(),
            "allowed": bool(allowed),
            "enforcement": "terminal-command-policy",
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "enforcement": "terminal-command-policy",
            "kernel_network_isolation": False,
        }
