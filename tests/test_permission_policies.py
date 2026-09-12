import pytest
from pydantic import ValidationError

from app.capabilities.templates import ResourceType, RiskLevel
from app.permissions.policies import (
    APPROVED_PERMISSION_POLICIES,
    PermissionDecision,
    PermissionPolicy,
    PermissionPolicyRegistry,
    PermissionScope,
    PermissionScopeKind,
)


def make_policy(**overrides):
    values = {
        "permission_id": "permission.file.read",
        "capability_id": "file.read",
        "resource_type": ResourceType.FILE,
        "operation": "READ",
        "scope": PermissionScope(
            resource_type=ResourceType.FILE,
            kind=PermissionScopeKind.TASK,
            selector="current_task.resource",
        ),
        "risk_level": RiskLevel.LOW,
        "decision": PermissionDecision.ALLOW,
    }
    values.update(overrides)
    return PermissionPolicy(**values)


def test_valid_permission_policy_can_be_created():
    policy = make_policy()

    assert policy.permission_id == "permission.file.read"
    assert policy.capability_id == "file.read"
    assert policy.scope.kind == PermissionScopeKind.TASK
    assert policy.decision == PermissionDecision.ALLOW


@pytest.mark.parametrize(
    "field, value",
    [
        ("permission_id", ""),
        ("permission_id", "file.read"),
        ("capability_id", "admin.execute"),
        ("operation", "DELETE"),
        ("risk_level", "CRITICAL"),
        ("decision", "MAYBE"),
    ],
)
def test_invalid_permission_fields_are_rejected(field, value):
    with pytest.raises((ValidationError, ValueError)):
        make_policy(**{field: value})


def test_invalid_scope_is_rejected():
    with pytest.raises((ValidationError, ValueError)):
        PermissionScope(
            resource_type=ResourceType.FILE,
            kind=PermissionScopeKind.RESOURCE,
            selector="*",
        )


def test_absolute_scope_is_rejected():
    with pytest.raises((ValidationError, ValueError)):
        PermissionScope(
            resource_type=ResourceType.FILE,
            kind=PermissionScopeKind.RESOURCE,
            selector="C:\\Users\\user\\secret.txt",
        )


def test_developer_file_policies_load_for_every_m3_file_capability():
    registry = PermissionPolicyRegistry()

    assert [policy.capability_id for policy in registry.list()] == [
        "file.list", "file.read", "file.create", "file.write", "file.delete",
        "file.move", "file.rename",
    ]
    assert len(registry.list()) == len(APPROVED_PERMISSION_POLICIES)


def test_policies_reference_existing_capabilities_and_matching_metadata():
    for policy in APPROVED_PERMISSION_POLICIES:
        assert policy.capability_id.startswith("file.")
        assert policy.resource_type == ResourceType.FILE
        assert policy.scope.resource_type == ResourceType.FILE
        assert policy.risk_level in RiskLevel


def test_duplicate_permission_ids_are_rejected():
    policy = make_policy()

    with pytest.raises(ValueError, match="DUPLICATE_PERMISSION"):
        PermissionPolicyRegistry([policy, policy])


def test_policy_cannot_silently_grant_a_different_capability():
    with pytest.raises(ValueError, match="operation does not match"):
        make_policy(capability_id="file.read", operation="DELETE")

    with pytest.raises(ValueError, match="risk_level does not match"):
        make_policy(capability_id="file.delete", operation="DELETE", risk_level=RiskLevel.LOW)


def test_llm_style_permission_definition_is_rejected():
    with pytest.raises((ValidationError, ValueError)):
        make_policy(
            permission_id="permission.llm.generated",
            capability_id="admin.execute",
            operation="EXECUTE",
        )


def test_policy_registry_returns_defensive_copies():
    registry = PermissionPolicyRegistry()
    returned = registry.get("permission.file.read")

    with pytest.raises(ValidationError):
        returned.operation = "DELETE"

    with pytest.raises(TypeError, match="immutable"):
        returned.metadata["decision"] = "ALLOW_ALL"
    assert "decision" not in registry.get("permission.file.read").metadata


def test_approved_policy_collection_cannot_be_structurally_mutated():
    with pytest.raises(AttributeError):
        APPROVED_PERMISSION_POLICIES.append(make_policy())


def test_permission_definitions_are_data_only():
    for policy in APPROVED_PERMISSION_POLICIES:
        assert not hasattr(policy, "execute")
        assert not hasattr(policy, "run")
        assert callable(getattr(policy, "model_dump", None))
