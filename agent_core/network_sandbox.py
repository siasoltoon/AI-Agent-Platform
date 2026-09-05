"""Native network containment boundary for agent processes.

Command-level network policy cannot prevent every interpreter or library escape.
This module provides an explicit native mode where the host supports it and
fails closed when native containment cannot be established.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Sequence


class NetworkSandboxError(PermissionError):
    """Raised when requested native network containment cannot be enforced."""


@dataclass(frozen=True)
class NetworkSandbox:
    """Describe and apply process-level native network isolation."""

    mode: str = "command-policy"

    def __post_init__(self) -> None:
        if self.mode not in {"none", "command-policy", "native", "fail-closed"}:
            raise ValueError("Network sandbox mode must be none, command-policy, native, or fail-closed.")

    @property
    def native_supported(self) -> bool:
        return os.name != "nt" and shutil.which("unshare") is not None

    def snapshot(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "native_supported": self.native_supported,
            "enforced": self.mode == "native" and self.native_supported,
            "mechanism": "linux-network-namespace" if self.native_supported else "unavailable",
        }

    def wrap(self, args: Sequence[str]) -> list[str]:
        """Wrap argv in a network namespace when native mode is requested."""
        if self.mode in {"none", "command-policy"}:
            return list(args)
        if not self.native_supported:
            raise NetworkSandboxError("Native network isolation is unavailable; refusing to execute.")
        # --net creates a fresh network namespace with no inherited interfaces.
        return ["unshare", "--net", "--", *args]
