from __future__ import annotations

from app.capabilities.registry import CapabilityRegistry, CapabilityRegistryError
from app.capabilities.security import CapabilitySecurityValidator
from app.intent.schemas import IntentCheckResult
from app.planner.schemas import PlanStep, PlannerIntent
from app.planner.schemas import TaskPlan


class CapabilityResolver:
    """Resolve validated planner intents to approved capability templates."""

    def __init__(self, registry: CapabilityRegistry | None = None):
        self.registry = registry or CapabilityRegistry()
        self.security_validator = CapabilitySecurityValidator(self.registry)

    @staticmethod
    def _normalize_operation(operation: str) -> str:
        if not isinstance(operation, str) or not operation.strip():
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "A valid operation string is required to resolve a capability.",
            )
        # Only explicit, developer-reviewed aliases are accepted.  In
        # particular this is not a heuristic "uppercase whatever the model
        # said" conversion: unknown planner labels fail closed below.
        aliases = {
            "LIST": "LIST", "LIST_FILES": "LIST",
            "READ": "READ", "READ_FILE": "READ",
            "USER_REQUESTED_READ_DOCUMENTS": "READ",
            "CREATE": "CREATE", "CREATE_FILE": "CREATE",
            "WRITE": "WRITE", "WRITE_FILE": "WRITE",
            "MOVE": "MOVE", "MOVE_FILE": "MOVE",
            "RENAME": "RENAME", "RENAME_FILE": "RENAME",
            "DELETE": "DELETE", "DELETE_FILE": "DELETE",
        }
        normalized = operation.strip().upper()
        if normalized not in aliases:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                f"Planner operation '{operation}' has no approved canonical mapping.",
            )
        return aliases[normalized]

    def resolve(self, operation: str, *, resource: str | None = None, agent: str | None = None) -> object:
        normalized_operation = self._normalize_operation(operation)
        if normalized_operation in {"CLARIFY", "ASK_CLARIFICATION"}:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "Clarification steps do not resolve to an approved capability.",
            )

        matches = [
            template
            for template in self.registry.list()
            if template.operation.upper() == normalized_operation
        ]

        if agent is not None:
            matches = [template for template in matches if template.agent == agent]

        if resource is not None:
            resource_value = str(resource).strip()
            if resource_value:
                if resource_value.lower() in {"directory", "browser", "email"}:
                    raise CapabilityRegistryError(
                        "CAPABILITY_NOT_FOUND",
                        f"Resource type '{resource_value}' is not supported by the matching file capability.",
                    )
                matches = [
                    template for template in matches if template.resource_type.value == "file"
                ]

        if not matches:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                f"No approved capability matches operation '{operation}'.",
            )
        if len(matches) > 1:
            ids = ", ".join(sorted(template.capability_id for template in matches))
            raise CapabilityRegistryError(
                "AMBIGUOUS_CAPABILITY",
                f"Operation '{operation}' matches multiple approved capabilities: {ids}.",
            )

        return matches[0]

    def resolve_step(self, step: PlanStep):
        if not isinstance(step, PlanStep):
            raise TypeError("CapabilityResolver.resolve_step expects a PlanStep.")

        if step.intent == PlannerIntent.ASK_CLARIFICATION:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "The clarification step is not an approved capability.",
            )

        capability = self.resolve(
            step.operation,
            resource=step.resource,
            agent=step.agent,
        )
        return self.security_validator.validate(capability, step=step)

    def resolve_validated_plan(
        self,
        task_plan: TaskPlan,
        intent_result: IntentCheckResult,
    ) -> list:
        if not isinstance(task_plan, TaskPlan):
            raise TypeError("CapabilityResolver.resolve_validated_plan expects a TaskPlan.")
        if not isinstance(intent_result, IntentCheckResult):
            raise TypeError(
                "CapabilityResolver.resolve_validated_plan expects an IntentCheckResult."
            )
        if intent_result.task_id != task_plan.task_id:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "The intent result does not belong to the supplied TaskPlan.",
            )
        if not intent_result.consistent or intent_result.mismatched_steps:
            raise CapabilityRegistryError(
                "CAPABILITY_NOT_FOUND",
                "An inconsistent task plan cannot produce approved capabilities.",
            )

        return [self.resolve_step(step) for step in task_plan.steps]


__all__ = [
    "CapabilityResolver",
]
