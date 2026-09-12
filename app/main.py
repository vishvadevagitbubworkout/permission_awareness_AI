from app.capabilities.registry import CapabilityRegistryError
from app.capabilities.templates import ResourceType
from app.intent.parsing import IntentParsingError
from app.intent.schemas import IntentCheckResult
from app.intent.validator import IntentValidator
from app.permissions.authorization import TaskAuthorizationManager
from app.permissions.policies import PermissionScope, PermissionScopeKind
from app.planner.ollama_client import OllamaError
from app.planner.planner import Planner
from app.planner.parsing import PlanParsingError
from app.planner.schemas import TaskPlan
from app.pipeline import M1M5Pipeline


def format_plan(plan: TaskPlan) -> str:
	lines = [
		"Generated Plan:",
		"",
		f"Task ID: {plan.task_id}",
		"",
	]

	for index, step in enumerate(plan.steps, start=1):
		lines.extend(
			[
				f"Step {index}",
				f"Agent: {step.agent}",
				f"Operation: {step.operation}",
				f"Template: {step.template.value if step.template else 'legacy/unspecified'}",
				f"Intent: {step.intent.value if step.intent else 'legacy/unspecified'}",
				f"Resource: {step.resource}",
				f"Opaque File Refs: {step.opaque_file_refs}",
				f"Description: {step.description or 'legacy/unspecified'}",
				f"Confidence: {step.confidence if step.confidence is not None else 'legacy/unspecified'}",
				"Parameters:",
			]
		)
		if step.parameters:
			lines.extend(
				f"{key}: {value}" for key, value in step.parameters.items()
			)
		else:
			lines.append("{}")
		lines.append("")

	return "\n".join(lines).rstrip()


def format_intent_result(result: IntentCheckResult) -> str:
	status = "CONSISTENT" if result.consistent else "INCONSISTENT"
	lines = [
		"Intent Validation:",
		"",
		f"Status: {status}",
		"",
		"Reason:",
		result.reason,
	]
	if result.mismatched_steps:
		lines.extend(["", "Mismatched Steps:", *result.mismatched_steps])
	return "\n".join(lines)


def format_capabilities(capabilities) -> str:
	lines = ["Approved Capabilities:", ""]
	for index, capability in enumerate(capabilities, start=1):
		lines.append(f"{index}. {capability.capability_id}")
	return "\n".join(lines)


def format_authorization_results(results) -> str:
	lines = ["Task Authorization:", ""]
	for result in results:
		lines.append(
			f"{result.task_id}/{result.step_id}: {result.decision.value} "
			f"({result.capability_id or 'unresolved'})"
		)
		lines.append(f"Reason: {result.reason}")
	return "\n".join(lines)


def main() -> int:
	print("# LOCAL-FIRST AI AUTOMATION")
	user_request = input("Task:\n> ").strip()

	try:
		plan, intent_result, security_results = M1M5Pipeline().run(user_request)
	except (
		OllamaError,
		PlanParsingError,
		IntentParsingError,
		CapabilityRegistryError,
		ValueError,
	) as error:
		print(f"Planning failed: {error}")
		return 1

	print()
	print(format_plan(plan))
	print()
	print(format_intent_result(intent_result))
	print()
	print("M5 Security Results:")
	for result in security_results:
		print(f"{result.step_id}: {result.decision} ({result.capability_id or 'unresolved'})")
		print(f"Reason: {result.reason}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
