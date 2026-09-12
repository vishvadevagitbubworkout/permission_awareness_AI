import re

from app.intent.parsing import parse_intent_result
from app.intent.prompts import build_intent_prompt
from app.intent.schemas import IntentCheckResult, ValidatedIntentResult, _issue_validated_intent
from app.planner.ollama_client import OllamaClient
from app.planner.schemas import PlannerIntent, TaskPlan


_FILE_NAME = re.compile(r"\b[\w.-]+\.(?:pdf|docx?|xlsx?|txt)\b", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b", re.I)
_BROAD_SCOPE = re.compile(
    r"\b(?:all|entire|whole)\s+(?:files?|documents?|directory|folder)\b",
    re.I,
)

_TEMPLATE_CONTRACTS = {
    "FILE_LIST": ("LIST", "LIST"),
    "FILE_READ": ("READ", "READ"),
    "FILE_MOVE": ("MOVE", "MOVE"),
    "FILE_RENAME": ("RENAME", "RENAME"),
    "FILE_CREATE": ("CREATE", "CREATE"),
    "FILE_WRITE": ("WRITE", "WRITE"),
    "FILE_DELETE": ("DELETE", "DELETE"),
    "BROWSER_OPEN": ("BROWSER_OPEN", "BROWSER_OPEN"),
    "EMAIL_DRAFT": ("EMAIL_DRAFT", "EMAIL_DRAFT"),
    "EMAIL_SEND": ("EMAIL_SEND", "EMAIL_SEND"),
}


def _deterministic_mismatches(task_plan: TaskPlan) -> list[str]:
    request = task_plan.original_request
    requested_files = {match.lower() for match in _FILE_NAME.findall(request)}
    requested_recipients = {match.lower() for match in _EMAIL.findall(request)}
    mismatches = []

    for step in task_plan.steps:
        step_text = " ".join(
            str(value)
            for value in (
                step.resource,
                step.description,
                step.parameters,
            )
            if value is not None
        )
        if requested_files and _BROAD_SCOPE.search(step_text):
            mismatches.append(step.step_id)
            continue
        step_files = {match.lower() for match in _FILE_NAME.findall(step_text)}
        if requested_files and step_files and not step_files.intersection(requested_files):
            mismatches.append(step.step_id)
            continue
        step_recipients = {match.lower() for match in _EMAIL.findall(step_text)}
        if requested_recipients and step_recipients:
            if not step_recipients.intersection(requested_recipients):
                mismatches.append(step.step_id)

    return mismatches


def _deterministic_contract_mismatches(task_plan: TaskPlan) -> list[str]:
    mismatches = []
    for step in task_plan.steps:
        if step.template is None or step.intent is None:
            continue
        contract = _TEMPLATE_CONTRACTS.get(step.template.value)
        if contract is None:
            mismatches.append(step.step_id)
            continue
        expected_operation, expected_intent = contract
        # A reviewed legacy planner label may reach M2 from older M1 versions;
        # normalize only that exact label, never arbitrary operation text.
        operation = step.operation.upper()
        if operation == "USER_REQUESTED_READ_DOCUMENTS":
            operation = "READ"
        if operation != expected_operation or step.intent.value != expected_intent:
            mismatches.append(step.step_id)
    return mismatches


def _validated(result: IntentCheckResult, task_plan: TaskPlan) -> ValidatedIntentResult:
    return _issue_validated_intent(result, task_plan)


class IntentValidator:
    """Check whether a TaskPlan represents its original user request."""

    def __init__(self, ollama_client: OllamaClient | None = None):
        self.ollama_client = ollama_client or OllamaClient()

    def validate(self, task_plan: TaskPlan) -> ValidatedIntentResult:
        if not isinstance(task_plan, TaskPlan):
            raise TypeError("IntentValidator.validate expects a TaskPlan.")
        if not task_plan.task_id.strip():
            raise ValueError("The TaskPlan has no task ID.")
        if not task_plan.original_request.strip():
            raise ValueError("The TaskPlan has no original request.")

        step_ids = [step.step_id for step in task_plan.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("The TaskPlan contains duplicate step IDs.")

        for step in task_plan.steps:
            if not step.step_id.strip():
                raise ValueError("A TaskPlan step has no step ID.")
            if not step.agent.strip():
                raise ValueError("A TaskPlan step has no agent.")
            if not step.operation.strip():
                raise ValueError("A TaskPlan step has no operation.")

        if not task_plan.steps:
            return _validated(IntentCheckResult(
                task_id=task_plan.task_id,
                consistent=False,
                reason=(
                    "The plan contains no steps capable of fulfilling the "
                    "user's request."
                ),
                mismatched_steps=[],
            ), task_plan)

        if any(step.intent == PlannerIntent.ASK_CLARIFICATION for step in task_plan.steps):
            return _validated(IntentCheckResult(
                task_id=task_plan.task_id,
                consistent=False,
                reason=(
                    "The planner requested clarification because the supported intent vocabulary "
                    "does not include the requested operation."
                ),
                mismatched_steps=[
                    step.step_id
                    for step in task_plan.steps
                    if step.intent == PlannerIntent.ASK_CLARIFICATION
                ],
            ), task_plan)

        raw_response = self.ollama_client.generate(build_intent_prompt(task_plan))
        result = parse_intent_result(raw_response)
        if result.task_id != task_plan.task_id:
            raise ValueError(
                "The intent response task ID does not match the supplied TaskPlan."
            )
        known_step_ids = {step.step_id for step in task_plan.steps}
        unknown_step_ids = set(result.mismatched_steps).difference(known_step_ids)
        if unknown_step_ids:
            raise ValueError(
            "The intent response contains mismatched step IDs not present in the TaskPlan."
            )
        deterministic_mismatches = list(
            dict.fromkeys(
                _deterministic_mismatches(task_plan)
                + _deterministic_contract_mismatches(task_plan)
            )
        )
        if deterministic_mismatches:
            merged_steps = list(
                dict.fromkeys(result.mismatched_steps + deterministic_mismatches)
            )
            if result.consistent:
                return _validated(result.model_copy(
                    update={
                        "consistent": False,
                        "reason": (
                            "The plan broadens or changes a resource/entity named "
                            "in the user's request."
                        ),
                        "mismatched_steps": merged_steps,
                    }
                ), task_plan)
            return _validated(result.model_copy(update={"mismatched_steps": merged_steps}), task_plan)
        return _validated(result, task_plan)
