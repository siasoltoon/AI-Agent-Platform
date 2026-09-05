"""Deterministic network capability negotiation for mission execution."""

from __future__ import annotations

from dataclasses import dataclass


class NetworkCapabilityError(PermissionError):
    """Raised when a requested network capability would weaken the contract."""


_ALLOWED = {"deny", "restricted", "native", "allow"}
_RANK = {"deny": 0, "restricted": 1, "native": 2, "allow": 3}


@dataclass(frozen=True)
class NetworkCapability:
    """Normalize and validate the network capability requested by a mission."""

    mode: str = "restricted"

    def __post_init__(self) -> None:
        if self.mode not in _ALLOWED:
            raise ValueError("Network capability must be deny, restricted, native, or allow.")

    @classmethod
    def from_contract(cls, contract_mode: str | None) -> "NetworkCapability":
        return cls(str(contract_mode or "restricted").strip().lower())

    def authorize(self, requested_mode: str | None) -> "NetworkCapability":
        """Allow equal/stronger restrictions, but never allow capability escalation."""
        requested = str(requested_mode or self.mode).strip().lower()
        if requested not in _ALLOWED:
            raise ValueError("Requested network capability must be deny, restricted, native, or allow.")
        if _RANK[requested] > _RANK[self.mode]:
            raise NetworkCapabilityError(
                f"Requested network capability '{requested}' exceeds mission contract '{self.mode}'."
            )
        return NetworkCapability(requested)

    def snapshot(self) -> dict[str, object]:
        return {
            "contract_mode": self.mode,
            "allowed_modes": sorted(_ALLOWED, key=lambda value: _RANK[value]),
            "escalation_blocked": True,
        }
