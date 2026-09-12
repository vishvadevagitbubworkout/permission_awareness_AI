"""The non-executing M1--M5 integration boundary.

This module deliberately stops after capability verification/consumption.  M6
must present an actual action to a future runtime verifier; no filesystem or
desktop operation is performed here.
"""
from dataclasses import dataclass

from app.capabilities.templates import ResourceType
from app.intent.validator import IntentValidator
from app.permissions.authorization import TaskAuthorizationManager
from app.permissions.policies import PermissionDecision, PermissionScope, PermissionScopeKind
from app.planner.planner import Planner
from app.security.lifecycle import CapabilityLifecycleStore
from app.security.minting import CapabilityMinter
from app.security.verification import CapabilityVerifier


@dataclass(frozen=True)
class PipelineStepResult:
    step_id: str
    decision: str
    reason: str
    capability_id: str | None = None


class M1M5Pipeline:
    """Run the real module chain and return an auditable, non-executing result."""

    def __init__(self, *, planner=None, validator=None, authorizer=None,
                 minter=None, verifier=None, lifecycle=None):
        self.planner = planner or Planner()
        self.validator = validator or IntentValidator()
        self.authorizer = authorizer or TaskAuthorizationManager()
        self.minter = minter or CapabilityMinter(resolver=self.authorizer.resolver)
        self.verifier = verifier or CapabilityVerifier(key_provider=self.minter._key_provider)
        self.lifecycle = lifecycle or CapabilityLifecycleStore()

    def run(self, user_request: str) -> tuple[object, object, list[PipelineStepResult]]:
        plan = self.planner.create_plan(user_request)
        intent = self.validator.validate(plan)
        results = []
        for step in plan.steps:
            scope = None if step.resource is None else PermissionScope(
                resource_type=ResourceType.FILE, kind=PermissionScopeKind.TASK,
                selector="current_task.resource", resource_id=step.resource,
            )
            authorization = self.authorizer.authorize_step(plan, intent, step.step_id, scope=scope)
            if authorization.decision != PermissionDecision.ALLOW:
                results.append(PipelineStepResult(step.step_id, "DENY", authorization.reason))
                continue
            capability = self.minter.mint(authorization, plan, step)
            verified = self.verifier.verify(
                capability, expected_task_id=plan.task_id, expected_step_id=step.step_id,
                expected_agent=step.agent, expected_operation=capability.claims.operation,
                expected_resource=step.resource, expected_scope=authorization.scope,
            )
            self.lifecycle.verify_and_consume(verified)
            results.append(PipelineStepResult(step.step_id, "ALLOW", "M5 verified active capability.", capability.claims.capability_id))
        return plan, intent, results
