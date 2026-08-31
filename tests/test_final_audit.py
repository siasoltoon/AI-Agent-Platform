from agent_core.final_audit import FinalPlatformAudit


def test_required_modules_audit():
    audit = FinalPlatformAudit()
    result = audit.audit_module_names(audit.REQUIRED_MODULES)
    assert result.passed


def test_graph_dependency_audit():
    result = FinalPlatformAudit.audit_graph(["a", "b"], {"b": {"a"}})
    assert result.passed
    bad = FinalPlatformAudit.audit_graph(["a"], {"a": {"missing"}})
    assert not bad.passed


def test_completion_contract():
    audit = FinalPlatformAudit()
    assert audit.audit_completion_contract(status="completed", verified=True, blockers=[]).passed
    assert not audit.audit_completion_contract(status="completed", verified=False, blockers=[]).passed
