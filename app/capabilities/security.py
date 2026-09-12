from __future__ import annotations

from app.capabilities.registry import CapabilityRegistry, CapabilityRegistryError
from app.capabilities.templates import CapabilityTemplateDefinition
from app.planner.schemas import CapabilityTemplate, PlanStep, PlannerIntent

_TEMPLATE_TO_CAPABILITY = {
    CapabilityTemplate.FILE_LIST: ("LIST", "file.list"),
    CapabilityTemplate.FILE_READ: ("READ", "file.read"),
    CapabilityTemplate.FILE_MOVE: ("MOVE", "file.move"),
    CapabilityTemplate.FILE_RENAME: ("RENAME", "file.rename"),
    CapabilityTemplate.FILE_CREATE: ("CREATE", "file.create"),
    CapabilityTemplate.FILE_WRITE: ("WRITE", "file.write"),
    CapabilityTemplate.FILE_DELETE: ("DELETE", "file.delete"),
}


class CapabilitySecurityValidator:
    """Fail-closed validation for resolved, developer-defined capabilities."""

    def __init__(self, registry: CapabilityRegistry | None = None):
        self.registry = registry or CapabilityRegistry()

    def validate(
        self,
        capability: CapabilityTemplateDefinition,
        *,
        step: PlanStep | None = None,
    ) -> CapabilityTemplateDefinition:
        if not isinstance(capability, CapabilityTemplateDefinition):
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "The resolved value is not a capability template.",
            )

        canonical = self.registry.get(capability.capability_id)
        if capability != canonical:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "The capability does not exactly match its registered developer-defined template.",
            )

        if step is not None:
            self._validate_step(step, canonical)

        return canonical

    @staticmethod
    def _validate_step(step: PlanStep, capability: CapabilityTemplateDefinition) -> None:
        if not isinstance(step, PlanStep):
            raise TypeError("CapabilitySecurityValidator.validate expects a PlanStep.")
        if step.intent == PlannerIntent.ASK_CLARIFICATION:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "A clarification step cannot produce an approved capability.",
            )
        if step.template is not None:
            template_contract = _TEMPLATE_TO_CAPABILITY.get(step.template)
            if template_contract is None:
                raise CapabilityRegistryError(
                    "CAPABILITY_NOT_FOUND",
                    "The planner-declared template has no registered M3 capability.",
                )
            expected_operation, expected_capability_id = template_contract
            declared_operation = step.operation.upper()
            legacy_read_label = declared_operation == "USER_REQUESTED_READ_DOCUMENTS"
            if (
                (declared_operation != expected_operation and not (legacy_read_label and expected_operation == "READ"))
                or capability.capability_id != expected_capability_id
            ):
                raise CapabilityRegistryError(
                    "CAPABILITY_NOT_FOUND",
                    "The capability does not match the planner-declared template.",
                )
        normalized_step_operation = step.operation.upper()
        if normalized_step_operation == "USER_REQUESTED_READ_DOCUMENTS":
            normalized_step_operation = "READ"
        if step.agent != capability.agent or normalized_step_operation != capability.operation.upper():
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "The capability does not match the validated step agent and operation.",
            )
        if step.resource is not None and capability.resource_type.value != "file":
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "The capability does not match the validated step resource type.",
            )
        if step.parameters != capability.parameters:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "The capability parameters do not exactly match the registered template.",
            )


__all__ = ["CapabilitySecurityValidator"]
