from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from app.capabilities.registry import CapabilityRegistryError
from app.capabilities.resolver import CapabilityResolver
from app.intent.schemas import IntentCheckResult, ValidatedIntentResult
from app.permissions.evaluator import PermissionEvaluator
from app.permissions.policies import PermissionDecision, PermissionScope
from app.planner.schemas import TaskPlan


def _create_authorization_trust_boundary():
    """Closure-scoped issuance authority for M4 authorization results."""
    _integrity_token = object()

    def issue(**values) -> "AuthorizationResult":
        result = AuthorizationResult(**values)
        result._integrity_token = _integrity_token
        return result

    def is_integrity_valid(result: "AuthorizationResult") -> bool:
        return getattr(result, "_integrity_token", None) is _integrity_token

    return issue, is_integrity_valid


_issue_authorization, _authorization_is_integrity_valid = _create_authorization_trust_boundary()


class AuthorizationResult(BaseModel):
    """Immutable, task- and step-bound result produced by M4.3."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str | None
    step_id: str | None
    capability_id: str | None
    decision: PermissionDecision
    scope: PermissionScope | None
    reason: str = Field(..., min_length=1)
    _integrity_token: object | None = PrivateAttr(default=None)

    def is_integrity_valid(self) -> bool:
        return _authorization_is_integrity_valid(self)

    def model_copy(self, *, update=None, deep=False):
        if update:
            raise TypeError("AuthorizationResult cannot be retagged after authorization.")
        return super().model_copy(update=None, deep=deep)

    def is_bound_to(self, task_id: str, step_id: str) -> bool:
        return self.task_id == task_id and self.step_id == step_id


class TaskAuthorizationManager:
    """Bind M3/M4 decisions to the validated task and step that requested them."""

    def __init__(
        self,
        resolver: CapabilityResolver | None = None,
        evaluator: PermissionEvaluator | None = None,
    ):
        self.resolver = resolver or CapabilityResolver()
        self.evaluator = evaluator or PermissionEvaluator(
            capability_registry=self.resolver.registry,
        )

    def authorize_step(
        self,
        task_plan: TaskPlan,
        intent_result: IntentCheckResult,
        step_id: str,
        *,
        scope: PermissionScope | None,
    ) -> AuthorizationResult:
        task_id = task_plan.task_id if isinstance(task_plan, TaskPlan) else None
        if not task_id or not isinstance(step_id, str) or not step_id.strip():
            return self._deny(task_id, step_id, scope, "Missing task or step identity.")
        if not isinstance(intent_result, ValidatedIntentResult) or not intent_result.is_m2_validated():
            return self._deny(task_id, step_id, scope, "Missing validated M2 intent result.")
        if intent_result.task_id != task_id:
            return self._deny(task_id, step_id, scope, "The M2 task identity does not match the plan.")
        if not intent_result.is_bound_to_plan(task_plan):
            return self._deny(task_id, step_id, scope, "The M2 result does not match the validated task plan.")
        if not intent_result.consistent or step_id in intent_result.mismatched_steps:
            return self._deny(task_id, step_id, scope, "M2 did not validate this task step.")
        if scope is None or not isinstance(scope, PermissionScope):
            return self._deny(task_id, step_id, scope, "A valid authorization scope is required.")

        step = next((candidate for candidate in task_plan.steps if candidate.step_id == step_id), None)
        if step is None:
            return self._deny(task_id, step_id, scope, "The step is not part of the validated task.")
        if step.intent is None:
            return self._deny(task_id, step_id, scope, "The step has no validated planner intent.")
        if scope.resource_type.value != "file" or scope.resource_id != step.resource:
            return self._deny(task_id, step_id, scope, "The authorization scope does not match the task step resource.")

        try:
            capability = self.resolver.resolve_step(step)
            decision = self.evaluator.evaluate(
                capability,
                agent=step.agent,
                operation=capability.operation,
                resource_type=capability.resource_type,
                scope=scope,
                parameters=step.parameters,
                resource=step.resource,
            )
        except (CapabilityRegistryError, TypeError, ValueError, AttributeError) as error:
            return self._deny(
                task_id,
                step_id,
                scope,
                f"M3 resolution or M4 evaluation failed: {error}",
            )

        if decision == PermissionDecision.ALLOW:
            return _issue_authorization(
                task_id=task_id,
                step_id=step_id,
                capability_id=capability.capability_id,
                decision=decision,
                scope=scope,
                reason="The approved capability is permitted by the developer policy for this task scope.",
            )
        return self._deny(task_id, step_id, scope, "The capability is not permitted by the developer policy.")

    def authorize_plan(
        self,
        task_plan: TaskPlan,
        intent_result: IntentCheckResult,
        scopes: dict[str, PermissionScope | None],
    ) -> list[AuthorizationResult]:
        if not isinstance(task_plan, TaskPlan):
            return [self._deny(None, None, None, "Missing validated TaskPlan.")]
        return [
            self.authorize_step(
                task_plan,
                intent_result,
                step.step_id,
                scope=scopes.get(step.step_id),
            )
            for step in task_plan.steps
        ]

    @staticmethod
    def _deny(
        task_id: str | None,
        step_id: str | None,
        scope: PermissionScope | None,
        reason: str,
    ) -> AuthorizationResult:
        return _issue_authorization(
            task_id=task_id,
            step_id=step_id if isinstance(step_id, str) else None,
            capability_id=None,
            decision=PermissionDecision.DENY,
            scope=scope,
            reason=reason,
        )


__all__ = ["AuthorizationResult", "TaskAuthorizationManager"]
