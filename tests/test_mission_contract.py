from agent_core.mission_contract import MissionContract


def test_code_change_requires_tests():
    contract = MissionContract.from_objective("Implement a new authentication feature")
    assert contract.requires_tests
    assert contract.requires_inspection
    assert not contract.read_only


def test_read_only_audit_does_not_require_tests():
    contract = MissionContract.from_objective("Read-only audit of the repository")
    assert contract.read_only
    assert not contract.requires_tests
    assert contract.requires_execution_evidence


def test_docs_only_mission_does_not_force_tests():
    contract = MissionContract.from_objective("Update the README documentation only")
    assert not contract.requires_tests
    assert not contract.requires_build


def test_build_requirement_is_detected():
    contract = MissionContract.from_objective("Implement the frontend and run the production build")
    assert contract.requires_tests
    assert contract.requires_build
