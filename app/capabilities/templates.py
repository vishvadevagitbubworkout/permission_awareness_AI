from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ResourceType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    BROWSER = "browser"
    EMAIL = "email"


class CapabilityTemplateDefinition(BaseModel):
    """Developer-defined description of an approved capability.

    This model stores the metadata for a requestable capability but contains no
    execution logic. M3.1 is intentionally a registry/data-definition layer.
    """

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    operation: str = Field(..., min_length=1)
    resource_type: ResourceType
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel
    description: str = Field(..., min_length=1)


FILE_READ = CapabilityTemplateDefinition(
    capability_id="file.read",
    agent="file_manager",
    operation="READ",
    resource_type=ResourceType.FILE,
    parameters={"mode": "read"},
    risk_level=RiskLevel.LOW,
    description="Read a file resource without executing it.",
)

# These are the canonical, developer-owned file capabilities advertised to M1.
# They deliberately contain no executable code; M6 will be responsible for any
# filesystem implementation after M5 has verified a token.
FILE_LIST = CapabilityTemplateDefinition(
    capability_id="file.list", agent="file_manager", operation="LIST",
    resource_type=ResourceType.FILE, parameters={"mode": "list"},
    risk_level=RiskLevel.LOW, description="List a bounded file resource.",
)

FILE_MOVE = CapabilityTemplateDefinition(
    capability_id="file.move", agent="file_manager", operation="MOVE",
    resource_type=ResourceType.FILE, parameters={"mode": "move"},
    risk_level=RiskLevel.MEDIUM, description="Move a file within an approved scope.",
)

FILE_RENAME = CapabilityTemplateDefinition(
    capability_id="file.rename", agent="file_manager", operation="RENAME",
    resource_type=ResourceType.FILE, parameters={"mode": "rename"},
    risk_level=RiskLevel.MEDIUM, description="Rename a file within an approved scope.",
)

FILE_CREATE = CapabilityTemplateDefinition(
    capability_id="file.create",
    agent="file_manager",
    operation="CREATE",
    resource_type=ResourceType.FILE,
    parameters={"mode": "create"},
    risk_level=RiskLevel.MEDIUM,
    description="Create a new file resource without executing filesystem commands.",
)

FILE_WRITE = CapabilityTemplateDefinition(
    capability_id="file.write",
    agent="file_manager",
    operation="WRITE",
    resource_type=ResourceType.FILE,
    parameters={"mode": "write"},
    risk_level=RiskLevel.MEDIUM,
    description="Write content to an existing file resource without executing it.",
)

FILE_DELETE = CapabilityTemplateDefinition(
    capability_id="file.delete",
    agent="file_manager",
    operation="DELETE",
    resource_type=ResourceType.FILE,
    parameters={"mode": "delete"},
    risk_level=RiskLevel.HIGH,
    description="Delete a file resource without executing filesystem commands.",
)

APPROVED_CAPABILITY_TEMPLATES: list[CapabilityTemplateDefinition] = [
    FILE_LIST,
    FILE_READ,
    FILE_MOVE,
    FILE_RENAME,
    FILE_CREATE,
    FILE_WRITE,
    FILE_DELETE,
]

APPROVED_CAPABILITY_TEMPLATE_MAP: dict[str, CapabilityTemplateDefinition] = {
    template.capability_id: template for template in APPROVED_CAPABILITY_TEMPLATES
}

__all__ = [
    "APPROVED_CAPABILITY_TEMPLATE_MAP",
    "APPROVED_CAPABILITY_TEMPLATES",
    "CapabilityTemplateDefinition",
    "FILE_CREATE",
    "FILE_DELETE",
    "FILE_LIST",
    "FILE_MOVE",
    "FILE_RENAME",
    "FILE_READ",
    "FILE_WRITE",
    "ResourceType",
    "RiskLevel",
]
