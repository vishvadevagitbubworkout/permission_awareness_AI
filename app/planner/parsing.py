import json
import re
from collections.abc import Iterator
from typing import Any

from pydantic import ValidationError

from app.planner.schemas import PlannerIntent, TaskPlan


CONFIDENCE_THRESHOLD = 0.70
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_SHELL_COMMAND = re.compile(
    r"(^|\s)(cmd(?:\.exe)?|powershell(?:\.exe)?|bash|sh|rm|del|erase|python(?:\.exe)?|git)(\s|$)",
    re.I,
)
_OPAQUE_FILE_ID = re.compile(r"^file_[A-Za-z0-9_-]+$")
_FORBIDDEN_INSTRUCTION = re.compile(
    r"\b(generate\s+hmac|create\s+capabilit(?:y|ies)|mint\s+capabilit(?:y|ies)|"
    r"grant\s+permission|authorize\s+(?:this|the)\s+path|execute\s+command)\b",
    re.I,
)


def _string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _string_values(key)
            yield from _string_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _string_values(child)


class PlanParsingError(ValueError):
    """Raised when model output cannot become a complete TaskPlan."""


def parse_task_plan(
    raw_response: str, *, require_proposal_fields: bool = False
) -> TaskPlan:
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise PlanParsingError("The model returned an empty planning response.")

    normalized_response = raw_response.strip()
    # Models occasionally wrap otherwise valid JSON in a Markdown JSON fence.
    # Accept that presentation-only wrapper, but still require the enclosed
    # value to be one complete JSON object and validate it normally.
    if normalized_response.startswith("```json") and normalized_response.endswith("```"):
        normalized_response = normalized_response[7:-3].strip()
    try:
        payload = json.loads(normalized_response)
    except json.JSONDecodeError as error:
        raise PlanParsingError("The model returned invalid JSON.") from error

    if not isinstance(payload, dict):
        raise PlanParsingError("The planning response must be a JSON object.")

    raw_steps = payload.get("steps")
    required_proposal_fields = {
        "template",
        "intent",
        "opaque_file_refs",
        "parameters",
        "description",
        "confidence",
    }
    if require_proposal_fields and isinstance(raw_steps, list):
        for index, raw_step in enumerate(raw_steps, start=1):
            if isinstance(raw_step, dict):
                missing_fields = required_proposal_fields.difference(raw_step)
                if missing_fields:
                    missing = ", ".join(sorted(missing_fields))
                    raise PlanParsingError(
                        f"Planning step {index} is missing proposal fields: {missing}."
                    )

    try:
        if hasattr(TaskPlan, "model_validate"):
            plan = TaskPlan.model_validate(payload)
        else:
            plan = TaskPlan.parse_obj(payload)
    except ValidationError as error:
        raise PlanParsingError(
            f"The planning response does not match TaskPlan: {error}"
        ) from error

    if not plan.task_id.strip():
        raise PlanParsingError("The planning response has no task ID.")
    if not plan.original_request.strip():
        raise PlanParsingError("The planning response has no original request.")
    if not plan.steps:
        raise PlanParsingError("The planning response contains no steps.")

    for step in plan.steps:
        if not step.step_id.strip():
            raise PlanParsingError("A planning step has no step ID.")
        if not step.agent.strip():
            raise PlanParsingError("A planning step has no agent.")
        if not step.operation.strip():
            raise PlanParsingError("A planning step has no operation.")
        if step.opaque_file_refs and any(
            not _OPAQUE_FILE_ID.fullmatch(file_id)
            for file_id in step.opaque_file_refs
        ):
            raise PlanParsingError(
                "The planning response contains a malformed opaque file reference."
            )
        proposal_values = [
            step.agent,
            step.operation,
            step.resource,
            step.template.value if step.template else None,
            step.intent.value if step.intent else None,
            step.description,
            step.opaque_file_refs,
            step.parameters,
        ]
        for value in _string_values(proposal_values):
            if (
                value.startswith("/")
                or value.startswith("\\\\")
                or _WINDOWS_ABSOLUTE_PATH.match(value)
            ):
                raise PlanParsingError(
                    "The planning response contains an absolute filesystem path."
                )
            if _SHELL_COMMAND.search(value):
                raise PlanParsingError(
                    "The planning response contains a raw shell command."
                )
            if _FORBIDDEN_INSTRUCTION.search(value):
                raise PlanParsingError(
                    "The planning response contains a forbidden authority or execution instruction."
                )
        if step.confidence is not None and step.confidence < CONFIDENCE_THRESHOLD:
            step.intent = PlannerIntent.ASK_CLARIFICATION

    return plan
