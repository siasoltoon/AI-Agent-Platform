import pytest

from agent_core.network_capability import NetworkCapability, NetworkCapabilityError


def test_contract_defaults_to_restricted():
    capability = NetworkCapability.from_contract(None)
    assert capability.mode == "restricted"


def test_restriction_can_be_strengthened():
    capability = NetworkCapability("restricted")
    assert capability.authorize("deny").mode == "deny"


def test_capability_escalation_is_rejected():
    capability = NetworkCapability("restricted")
    with pytest.raises(NetworkCapabilityError, match="exceeds mission contract"):
        capability.authorize("allow")


def test_native_requires_explicit_contract_capability():
    capability = NetworkCapability("native")
    assert capability.authorize("native").mode == "native"
    assert capability.authorize("restricted").mode == "restricted"


def test_invalid_capability_is_rejected():
    with pytest.raises(ValueError):
        NetworkCapability("unknown")
    with pytest.raises(ValueError):
        NetworkCapability("restricted").authorize("unknown")
