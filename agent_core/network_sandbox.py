"""Native network containment boundary for agent processes.

Command-level network policy cannot prevent every interpreter or library escape.
This module provides an explicit native mode where the host supports it and
fails closed when native containment cannot be established.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence


class NetworkSandboxError(PermissionError):
    """Raised when requested native network containment cannot be enforced."""


@dataclass(frozen=True)
class NetworkSandbox:
    """Describe and apply process-level native network isolation."""

    mode: str = "command-policy"
    probe_timeout_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.mode not in {"none", "command-policy", "native", "fail-closed"}:
            raise ValueError("Network sandbox mode must be none, command-policy, native, or fail-closed.")
        if self.probe_timeout_seconds <= 0:
            raise ValueError("Network sandbox probe timeout must be positive.")

    @property
    def native_supported(self) -> bool:
        return os.name != "nt" and shutil.which("unshare") is not None

    def preflight(self) -> dict[str, object]:
        """Verify that the host can actually create a network namespace."""
        if not self.native_supported:
            return {
                "available": False,
                "mechanism": "unavailable",
                "reason": "unshare is unavailable on this host",
            }
        try:
            probe = subprocess.run(
                ["unshare", "--net", "--", "true"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self.probe_timeout_seconds,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "available": False,
                "mechanism": "linux-network-namespace",
                "reason": f"network namespace probe failed: {exc}",
            }
        if probe.returncode != 0:
            stderr = probe.stderr.decode(errors="replace").strip() if isinstance(probe.stderr, bytes) else str(probe.stderr or "").strip()
            return {
                "available": False,
                "mechanism": "linux-network-namespace",
                "reason": stderr or f"network namespace probe exited with code {probe.returncode}",
            }
        return {
            "available": True,
            "mechanism": "linux-network-namespace",
            "reason": "network namespace creation succeeded",
        }

    def snapshot(self) -> dict[str, object]:
        preflight = self.preflight() if self.mode in {"native", "fail-closed"} else None
        return {
            "mode": self.mode,
            "native_supported": self.native_supported,
            "native_available": bool(preflight and preflight["available"]),
            "enforced": self.mode == "native" and bool(preflight and preflight["available"]),
            "mechanism": "linux-network-namespace" if self.native_supported else "unavailable",
            "preflight_reason": preflight["reason"] if preflight else None,
        }

    def wrap(self, args: Sequence[str]) -> list[str]:
        """Wrap argv in a network namespace when native mode is requested."""
        if self.mode in {"none", "command-policy"}:
            return list(args)
        preflight = self.preflight()
        if not preflight["available"]:
            raise NetworkSandboxError(
                "Native network isolation is unavailable; refusing to execute: "
                + str(preflight["reason"])
            )
        # --net creates a fresh network namespace with no inherited interfaces.
        return ["unshare", "--net", "--", *args]
