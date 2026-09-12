from __future__ import annotations

from enum import Enum
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.capabilities.templates import (
    APPROVED_CAPABILITY_TEMPLATE_MAP,
    ResourceType,
    RiskLevel,
)


class _ImmutableMetadata(dict):
    def _blocked(self, *args, **kwargs):
        raise TypeError("permission metadata is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _blocked

    def __deepcopy__(self, memo):
        return self


class PermissionDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class PermissionScopeKind(str, Enum):
    RESOURCE = "resource"
    TASK = "task"


class PermissionScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_type: ResourceType
    kind: PermissionScopeKind
    selector: str = Field(..., min_length=1)
    resource_id: str | None = None

    @field_validator("selector")
    @classmethod
    def validate_selector(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("scope selector must not be empty")
        if "*" in normalized:
            raise ValueError("wildcard scopes are not allowed")
        if normalized.startswith(("/", "\\")) or (len(normalized) > 1 and normalized[1] == ":"):
            raise ValueError("absolute scope selectors are not allowed")
        return normalized

    @field_validator("resource_id")
    @classmethod
    def validate_resource_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized or "*" in normalized:
            raise ValueError("resource_id must be a non-empty, non-wildcard value")
        if normalized.startswith(("/", "\\")) or (len(normalized) > 1 and normalized[1] == ":"):
            raise ValueError("absolute resource IDs are not allowed")
        return normalized


class PermissionPolicy(BaseModel):
    """Developer-defined permission metadata for one approved capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    permission_id: str = Field(..., min_length=1)
    capability_id: str = Field(..., min_length=1)
    resource_type: ResourceType
    operation: str = Field(..., min_length=1)
    scope: PermissionScope
    risk_level: RiskLevel
    decision: PermissionDecision
    metadata: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="after")
    @classmethod
    def freeze_metadata(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return _ImmutableMetadata(value)

    @field_validator("permission_id")
    @classmethod
    def validate_permission_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or normalized != value:
            raise ValueError("permission_id must be a non-empty identifier without surrounding whitespace")
        if not normalized.startswith("permission."):
            raise ValueError("permission_id must use the permission.<name> format")
        return normalized

    @model_validator(mode="after")
    def validate_against_capability(self) -> "PermissionPolicy":
        template = APPROVED_CAPABILITY_TEMPLATE_MAP.get(self.capability_id)
        if template is None:
            raise ValueError(
                f"capability_id '{self.capability_id}' is not an approved capability"
            )
        if self.resource_type != template.resource_type:
            raise ValueError("resource_type does not match the referenced capability")
        if self.operation.upper() != template.operation.upper():
            raise ValueError("operation does not match the referenced capability")
        if self.risk_level != template.risk_level:
            raise ValueError("risk_level does not match the referenced capability")
        if self.scope.resource_type != template.resource_type:
            raise ValueError("scope resource_type does not match the referenced capability")
        return self


class PermissionPolicyRegistry:
    """Controlled collection of developer-defined permission policies."""

    def __init__(self, policies: list[PermissionPolicy] | None = None):
        self._policies: dict[str, PermissionPolicy] = {}
        source = list(policies) if policies is not None else list(APPROVED_PERMISSION_POLICIES)
        for policy in source:
            self.register(policy)

    def register(self, policy: PermissionPolicy) -> PermissionPolicy:
        if not isinstance(policy, PermissionPolicy):
            raise TypeError("PermissionPolicyRegistry.register expects a PermissionPolicy.")
        if policy.permission_id in self._policies:
            raise ValueError(
                f"DUPLICATE_PERMISSION: policy '{policy.permission_id}' is already registered"
            )
        self._policies[policy.permission_id] = policy.model_copy(deep=True)
        return policy.model_copy(deep=True)

    def get(self, permission_id: str) -> PermissionPolicy:
        policy = self._policies.get(permission_id)
        if policy is None:
            raise ValueError(f"PERMISSION_NOT_FOUND: policy '{permission_id}' is not registered")
        return policy.model_copy(deep=True)

    def list(self) -> list[PermissionPolicy]:
        return [policy.model_copy(deep=True) for policy in self._policies.values()]


APPROVED_PERMISSION_POLICIES: tuple[PermissionPolicy, ...] = (
    PermissionPolicy(permission_id="permission.file.list", capability_id="file.list", resource_type=ResourceType.FILE, operation="LIST", scope=PermissionScope(resource_type=ResourceType.FILE, kind=PermissionScopeKind.TASK, selector="current_task.resource"), risk_level=RiskLevel.LOW, decision=PermissionDecision.ALLOW, metadata={"source": "developer", "stage": "M4.2"}),
    PermissionPolicy(
        permission_id="permission.file.read",
        capability_id="file.read",
        resource_type=ResourceType.FILE,
        operation="READ",
        scope=PermissionScope(
            resource_type=ResourceType.FILE,
            kind=PermissionScopeKind.TASK,
            selector="current_task.resource",
        ),
        risk_level=RiskLevel.LOW,
        decision=PermissionDecision.ALLOW,
        metadata={"source": "developer", "stage": "M4.1"},
    ),
    PermissionPolicy(
        permission_id="permission.file.create",
        capability_id="file.create",
        resource_type=ResourceType.FILE,
        operation="CREATE",
        scope=PermissionScope(
            resource_type=ResourceType.FILE,
            kind=PermissionScopeKind.TASK,
            selector="current_task.resource",
        ),
        risk_level=RiskLevel.MEDIUM,
        decision=PermissionDecision.ALLOW,
        metadata={"source": "developer", "stage": "M4.1"},
    ),
    PermissionPolicy(
        permission_id="permission.file.write",
        capability_id="file.write",
        resource_type=ResourceType.FILE,
        operation="WRITE",
        scope=PermissionScope(
            resource_type=ResourceType.FILE,
            kind=PermissionScopeKind.TASK,
            selector="current_task.resource",
        ),
        risk_level=RiskLevel.MEDIUM,
        decision=PermissionDecision.ALLOW,
        metadata={"source": "developer", "stage": "M4.1"},
    ),
    PermissionPolicy(
        permission_id="permission.file.delete",
        capability_id="file.delete",
        resource_type=ResourceType.FILE,
        operation="DELETE",
        scope=PermissionScope(
            resource_type=ResourceType.FILE,
            kind=PermissionScopeKind.TASK,
            selector="current_task.resource",
        ),
        risk_level=RiskLevel.HIGH,
        decision=PermissionDecision.ALLOW,
        metadata={"source": "developer", "stage": "M4.1"},
    ),
    PermissionPolicy(permission_id="permission.file.move", capability_id="file.move", resource_type=ResourceType.FILE, operation="MOVE", scope=PermissionScope(resource_type=ResourceType.FILE, kind=PermissionScopeKind.TASK, selector="current_task.resource"), risk_level=RiskLevel.MEDIUM, decision=PermissionDecision.ALLOW, metadata={"source": "developer", "stage": "M4.2"}),
    PermissionPolicy(permission_id="permission.file.rename", capability_id="file.rename", resource_type=ResourceType.FILE, operation="RENAME", scope=PermissionScope(resource_type=ResourceType.FILE, kind=PermissionScopeKind.TASK, selector="current_task.resource"), risk_level=RiskLevel.MEDIUM, decision=PermissionDecision.ALLOW, metadata={"source": "developer", "stage": "M4.2"}),
)


__all__ = [
    "APPROVED_PERMISSION_POLICIES",
    "PermissionDecision",
    "PermissionPolicy",
    "PermissionPolicyRegistry",
    "PermissionScope",
    "PermissionScopeKind",
]
