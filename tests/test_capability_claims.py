from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.capabilities.templates import ResourceType
from app.permissions.policies import PermissionScope, PermissionScopeKind
from app.security.capabilities import CapabilityClaims, UsagePolicy


NOW = datetime.now(timezone.utc)


def make_scope(resource_id="report.pdf"):
    return PermissionScope(
        resource_type=ResourceType.FILE,
        kind=PermissionScopeKind.TASK,
        selector="current_task.resource",
        resource_id=resource_id,
    )


def make_claims(**overrides):
    values = {
        "capability_id": "file.read",
        "task_id": "task_001",
        "step_id": "step_001",
        "agent": "file_manager",
        "operation": "READ",
        "resource": "report.pdf",
        "scope": make_scope(),
        "constraints": {"mode": "read", "max_files": 1},
        "issued_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "nonce": "0123456789abcdef",
        "usage_policy": UsagePolicy.ONE_TIME,
    }
    values.update(overrides)
    return CapabilityClaims(**values)


def test_valid_capability_claims_can_be_constructed():
    claims = make_claims()

    assert claims.capability_id == "file.read"
    assert claims.task_id == "task_001"
    assert claims.scope.resource_id == "report.pdf"
    assert claims.usage_policy == UsagePolicy.ONE_TIME


def test_bounded_resource_labels_may_contain_spaces_but_not_path_traversal():
    claims = make_claims(resource="document folder")
    assert claims.resource == "document folder"
    with pytest.raises(ValueError, match="bounded relative resource"):
        make_claims(resource="../Secrets")


def test_valid_repeatable_usage_policy_is_accepted():
    assert make_claims(usage_policy=UsagePolicy.REPEATABLE).usage_policy == UsagePolicy.REPEATABLE


def test_missing_required_claims_are_rejected():
    required = [
        "capability_id",
        "task_id",
        "step_id",
        "agent",
        "operation",
        "resource",
        "scope",
        "issued_at",
        "expires_at",
        "nonce",
        "usage_policy",
    ]
    for field in required:
        values = make_claims().model_dump()
        values.pop(field)
        with pytest.raises(ValidationError):
            CapabilityClaims(**values)


def test_unknown_capability_is_rejected():
    with pytest.raises(ValidationError, match="approved M3 capability"):
        make_claims(capability_id="file.format_disk", operation="FORMAT")


@pytest.mark.parametrize(
    "field, value",
    [
        ("task_id", ""),
        ("step_id", "step with spaces"),
        ("agent", ""),
        ("operation", "READ/DELETE"),
        ("resource", ""),
        ("nonce", "short"),
        ("usage_policy", "ACTIVE"),
    ],
)
def test_malformed_identifiers_and_usage_are_rejected(field, value):
    with pytest.raises(ValidationError):
        make_claims(**{field: value})


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_claims(issued_at=datetime.now())


def test_non_expiring_or_reverse_timestamps_are_rejected():
    with pytest.raises(ValidationError, match="expires_at"):
        make_claims(expires_at=NOW)
    with pytest.raises(ValidationError, match="expires_at"):
        make_claims(expires_at=NOW - timedelta(minutes=1))


def test_malformed_constraints_are_rejected():
    with pytest.raises(ValidationError):
        make_claims(constraints=["not", "an", "object"])
    with pytest.raises(ValidationError, match="constraint keys"):
        make_claims(constraints={"": "invalid"})
    with pytest.raises(ValidationError, match="JSON-compatible"):
        make_claims(constraints={"callable": lambda: None})


def test_scope_is_preserved_and_scope_resource_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="scope resource type"):
        make_claims(
            scope=PermissionScope(
                resource_type=ResourceType.DIRECTORY,
                kind=PermissionScopeKind.TASK,
                selector="current_task.resource",
                resource_id="report.pdf",
            )
        )


def test_constraints_are_immutable_including_nested_values():
    claims = make_claims(constraints={"nested": {"max_files": 1}, "items": ["report.pdf"]})

    with pytest.raises(TypeError, match="immutable"):
        claims.constraints["new"] = True
    with pytest.raises(TypeError, match="immutable"):
        claims.constraints["nested"]["max_files"] = 99
    assert claims.constraints["nested"]["max_files"] == 1


def test_capability_claims_are_immutable_and_not_retaggable():
    claims = make_claims()

    with pytest.raises(ValidationError):
        claims.task_id = "task_999"
    with pytest.raises(TypeError, match="retagged"):
        claims.model_copy(update={"task_id": "task_999", "agent": "browser_agent"})


def test_capability_claims_have_no_lifecycle_or_crypto_behavior():
    claims = make_claims()

    assert not hasattr(claims, "mac")
    assert not hasattr(claims, "hmac")
    assert not hasattr(claims, "verify")
    assert not hasattr(claims, "consume")
    assert not hasattr(claims, "state")
    assert not hasattr(claims, "execute")
