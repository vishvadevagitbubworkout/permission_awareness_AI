from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.capabilities.templates import APPROVED_CAPABILITY_TEMPLATE_MAP
from app.permissions.policies import PermissionScope

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_RESOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,127}$")
_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_MAC = re.compile(r"^[0-9a-f]{64}$")


class UsagePolicy(str, Enum):
    ONE_TIME = "ONE_TIME"
    REPEATABLE = "REPEATABLE"


class _ImmutableMapping(dict):
    def _blocked(self, *args, **kwargs):
        raise TypeError("capability constraints are immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _blocked

    def __deepcopy__(self, memo):
        return self


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return _ImmutableMapping({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    if isinstance(value, tuple):
        return tuple(_freeze(child) for child in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError("constraints must contain only JSON-compatible values")


class CapabilityClaims(BaseModel):
    """Immutable unsigned capability claims reserved for later M5 authentication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    step_id: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    operation: str = Field(..., min_length=1)
    resource: str = Field(..., min_length=1)
    scope: PermissionScope
    constraints: Mapping[str, Any] = Field(default_factory=dict)
    issued_at: datetime
    expires_at: datetime
    nonce: str = Field(..., min_length=16, max_length=128)
    usage_policy: UsagePolicy

    def model_copy(self, *, update=None, deep=False):
        if update:
            raise TypeError("CapabilityClaims cannot be retagged after creation")
        return super().model_copy(update=None, deep=deep)

    @field_validator("capability_id", "task_id", "step_id", "agent", "operation")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != value or not _IDENTIFIER.fullmatch(normalized):
            raise ValueError("capability identifiers must use the established safe identifier format")
        return normalized

    @field_validator("resource")
    @classmethod
    def validate_resource(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != value or not _RESOURCE.fullmatch(normalized) or ".." in normalized:
            raise ValueError("resource must be a bounded relative resource label")
        return normalized

    @field_validator("nonce")
    @classmethod
    def validate_nonce(cls, value: str) -> str:
        if not _NONCE.fullmatch(value):
            raise ValueError("nonce must be a 16-128 character URL-safe value")
        return value

    @field_validator("issued_at", "expires_at")
    @classmethod
    def validate_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability timestamps must be timezone-aware")
        return value

    @field_validator("constraints", mode="after")
    @classmethod
    def validate_constraints(cls, value: Any) -> Mapping[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("constraints must be a JSON object")
        if any(not isinstance(key, str) or not key.strip() for key in value):
            raise ValueError("constraint keys must be non-empty strings")
        return _freeze(value)

    @model_validator(mode="after")
    def validate_claim_relationships(self) -> "CapabilityClaims":
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at")
        template = APPROVED_CAPABILITY_TEMPLATE_MAP.get(self.capability_id)
        if template is None:
            raise ValueError("capability_id must reference an approved M3 capability")
        if self.agent != template.agent:
            raise ValueError("agent does not match the approved capability")
        if self.operation.upper() != template.operation.upper():
            raise ValueError("operation does not match the approved capability")
        if self.scope.resource_type != template.resource_type:
            raise ValueError("scope resource type does not match the approved capability")
        return self


class AuthenticatedCapability(BaseModel):
    """Immutable claims plus the M5.2 authentication tag."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claims: CapabilityClaims
    mac: str = Field(..., min_length=64, max_length=64)

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, value: str) -> str:
        if not _MAC.fullmatch(value):
            raise ValueError("mac must be a lowercase hexadecimal SHA-256 HMAC")
        return value

    def model_copy(self, *, update=None, deep=False):
        if update:
            raise TypeError("AuthenticatedCapability cannot be retagged after minting")
        return super().model_copy(update=None, deep=deep)


__all__ = ["AuthenticatedCapability", "CapabilityClaims", "UsagePolicy"]
