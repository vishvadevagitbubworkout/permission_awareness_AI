import pytest
from pydantic import ValidationError

from app.capabilities.templates import (
    APPROVED_CAPABILITY_TEMPLATES,
    CapabilityTemplateDefinition,
    ResourceType,
    RiskLevel,
)


def test_valid_capability_template_can_be_created():
    capability = CapabilityTemplateDefinition(
        capability_id="file.read",
        agent="file_manager",
        operation="READ",
        resource_type=ResourceType.FILE,
        parameters={"mode": "read"},
        risk_level=RiskLevel.LOW,
        description="Read a file.",
    )

    assert capability.capability_id == "file.read"
    assert capability.agent == "file_manager"
    assert capability.operation == "READ"
    assert capability.risk_level == RiskLevel.LOW


@pytest.mark.parametrize(
    "field_value, expected_message",
    [
        ({"capability_id": "", "agent": "file_manager", "operation": "READ", "resource_type": "file", "risk_level": "LOW", "description": "Read a file."}, "at least 1 character"),
        ({"capability_id": "file.read", "agent": "", "operation": "READ", "resource_type": "file", "risk_level": "LOW", "description": "Read a file."}, "at least 1 character"),
        ({"capability_id": "file.read", "agent": "file_manager", "operation": "", "resource_type": "file", "risk_level": "LOW", "description": "Read a file."}, "at least 1 character"),
        ({"capability_id": "file.read", "agent": "file_manager", "operation": "READ", "resource_type": "file", "risk_level": "LOW"}, "Field required"),
    ],
)
def test_missing_or_invalid_required_fields_are_rejected(field_value, expected_message):
    with pytest.raises((ValidationError, ValueError)):
        CapabilityTemplateDefinition(**field_value)


def test_invalid_risk_levels_are_rejected():
    with pytest.raises(ValidationError):
        CapabilityTemplateDefinition(
            capability_id="file.read",
            agent="file_manager",
            operation="READ",
            resource_type=ResourceType.FILE,
            risk_level="CRITICAL",
            description="Read a file.",
        )


def test_predefined_file_capabilities_have_expected_structure():
    assert [template.capability_id for template in APPROVED_CAPABILITY_TEMPLATES] == [
        "file.list", "file.read", "file.move", "file.rename",
        "file.create", "file.write", "file.delete",
    ]
    assert all(template.resource_type == ResourceType.FILE for template in APPROVED_CAPABILITY_TEMPLATES)
    assert all(template.parameters for template in APPROVED_CAPABILITY_TEMPLATES)


def test_templates_are_data_only_and_do_not_execute_operations():
    for template in APPROVED_CAPABILITY_TEMPLATES:
        assert not hasattr(template, "execute")
        assert not hasattr(template, "run")
        assert callable(getattr(template, "model_dump", None))
        assert "" not in (template.capability_id, template.description)
