import json

import pytest

from app.planner.parsing import PlanParsingError, parse_task_plan


def test_parse_task_plan_validates_json_into_task_plan():
    plan = parse_task_plan(
        '{"task_id":"task_001",'
        '"original_request":"Read report.pdf",'
        '"steps":[{"step_id":"step_001","agent":"file_agent",'
        '"operation":"READ","resource":"report.pdf",'
        '"parameters":{"location":"Documents"}}]}'
    )

    assert plan.task_id == "task_001"
    assert plan.steps[0].operation == "READ"


def test_parse_task_plan_accepts_json_fence_but_not_non_json_prose():
    plan = parse_task_plan(
        '```json\n{"task_id":"task_001","original_request":"Read report",'
        '"steps":[{"step_id":"step_001","agent":"file_agent","operation":"READ"}]}\n```'
    )
    assert plan.task_id == "task_001"


@pytest.mark.parametrize(
    "raw_response, expected_message",
    [
        ("not json", "invalid JSON"),
        ("[]", "JSON object"),
        ('{"task_id":"task_001"}', "does not match TaskPlan"),
        (
            '{"task_id":"task_001","original_request":"request","steps":[]}',
            "no steps",
        ),
        (
            '{"task_id":"","original_request":"request",'
            '"steps":[{"step_id":"step_001","agent":"file_agent",'
            '"operation":"READ"}]}',
            "no task ID",
        ),
    ],
)
def test_parse_task_plan_rejects_invalid_output(raw_response, expected_message):
    with pytest.raises(PlanParsingError, match=expected_message):
        parse_task_plan(raw_response)


def test_strict_planner_parsing_rejects_missing_proposal_fields():
    with pytest.raises(PlanParsingError, match="missing proposal fields"):
        parse_task_plan(
            '{"task_id":"task_001","original_request":"Read report",'
            '"steps":[{"step_id":"step_001","agent":"file_agent",'
            '"operation":"READ"}]}',
            require_proposal_fields=True,
        )


def test_low_confidence_step_routes_to_clarification():
    plan = parse_task_plan(
        '{"task_id":"task_001","original_request":"Find the invoice",'
        '"steps":[{"step_id":"step_001","agent":"file_agent",'
        '"operation":"LIST","intent":"READ","confidence":0.69}]}'
    )

    assert plan.steps[0].intent.value == "ASK_CLARIFICATION"


def test_valid_intent_and_normal_confidence_are_preserved():
    plan = parse_task_plan(
        '{"task_id":"task_001","original_request":"Read report.pdf",'
        '"steps":[{"step_id":"step_001","agent":"file_agent",'
        '"operation":"READ","intent":"READ","confidence":0.95}]}'
    )

    assert plan.steps[0].intent.value == "READ"
    assert plan.steps[0].confidence == 0.95


@pytest.mark.parametrize("confidence", [0.0, 0.50, 0.69])
def test_confidence_below_threshold_routes_to_clarification(confidence):
    plan = parse_task_plan(
        json.dumps(
            {
                "task_id": "task_001",
                "original_request": "Read report.pdf",
                "steps": [
                    {
                        "step_id": "step_001",
                        "agent": "file_agent",
                        "operation": "READ",
                        "intent": "READ",
                        "confidence": confidence,
                    }
                ],
            }
        )
    )

    assert plan.steps[0].intent.value == "ASK_CLARIFICATION"


@pytest.mark.parametrize("confidence", [0.70, 0.71, 1.0])
def test_confidence_at_or_above_threshold_preserves_intent(confidence):
    plan = parse_task_plan(
        json.dumps(
            {
                "task_id": "task_001",
                "original_request": "Read report.pdf",
                "steps": [
                    {
                        "step_id": "step_001",
                        "agent": "file_agent",
                        "operation": "READ",
                        "intent": "READ",
                        "confidence": confidence,
                    }
                ],
            }
        )
    )

    assert plan.steps[0].intent.value == "READ"


def test_template_and_opaque_file_reference_are_validated():
    plan = parse_task_plan(
        '{"task_id":"task_001","original_request":"Read report.pdf",'
        '"steps":[{"step_id":"step_001","agent":"file_agent",'
        '"operation":"READ","template":"FILE_READ","intent":"READ",'
        '"opaque_file_refs":["file_001"],"description":"Read report",'
        '"confidence":0.95}]}'
    )

    assert plan.steps[0].template.value == "FILE_READ"
    assert plan.steps[0].opaque_file_refs == ["file_001"]


def test_malformed_opaque_file_reference_is_rejected():
    with pytest.raises(PlanParsingError, match="malformed opaque file reference"):
        parse_task_plan(
            '{"task_id":"task_001","original_request":"Read report",'
            '"steps":[{"step_id":"step_001","agent":"file_agent",'
            '"operation":"READ","opaque_file_refs":["C:\\\\secret.txt"]}]}'
        )


@pytest.mark.parametrize(
    "instruction",
    ["generate HMAC", "grant permission", "create capability", "execute command"],
)
def test_authority_or_execution_instruction_is_rejected(instruction):
    with pytest.raises(PlanParsingError, match="forbidden authority"):
        parse_task_plan(
            json.dumps(
                {
                    "task_id": "task_001",
                    "original_request": "Read a report",
                    "steps": [
                        {
                            "step_id": "step_001",
                            "agent": "file_agent",
                            "operation": "READ",
                            "parameters": {"instruction": instruction},
                        }
                    ],
                }
            )
        )


def test_invalid_planner_intent_is_rejected():
    with pytest.raises(PlanParsingError, match="does not match TaskPlan"):
        parse_task_plan(
            '{"task_id":"task_001","original_request":"Read report",'
            '"steps":[{"step_id":"step_001","agent":"file_agent",'
            '"operation":"READ","intent":"FORMAT"}]}'
        )


@pytest.mark.parametrize("resource", ["C:\\Users\\user\\secret.txt", "/tmp/secret.txt"])
def test_absolute_resource_path_is_rejected(resource):
    with pytest.raises(PlanParsingError, match="absolute filesystem path"):
        parse_task_plan(
            json.dumps(
                {
                    "task_id": "task_001",
                    "original_request": "Read a file",
                    "steps": [
                        {
                            "step_id": "step_001",
                            "agent": "file_agent",
                            "operation": "READ",
                            "resource": resource,
                        }
                    ],
                }
            )
        )


@pytest.mark.parametrize("operation", ["powershell Get-ChildItem", "rm -rf secret.txt"])
def test_raw_shell_command_is_rejected(operation):
    with pytest.raises(PlanParsingError, match="raw shell command"):
        parse_task_plan(
            json.dumps(
                {
                    "task_id": "task_001",
                    "original_request": "Run a command",
                    "steps": [
                        {
                            "step_id": "step_001",
                            "agent": "shell_agent",
                            "operation": operation,
                        }
                    ],
                }
            )
        )


@pytest.mark.parametrize(
    "intent",
    [
        "LIST",
        "READ",
        "MOVE",
        "RENAME",
        "BROWSER_OPEN",
        "EMAIL_DRAFT",
        "EMAIL_SEND",
        "ASK_CLARIFICATION",
    ],
)
def test_all_paper_intents_are_accepted(intent):
    plan = parse_task_plan(
        json.dumps(
            {
                "task_id": "task_001",
                "original_request": "Perform the requested action",
                "steps": [
                    {
                        "step_id": "step_001",
                        "agent": "task_agent",
                        "operation": "planned_operation",
                        "intent": intent,
                    }
                ],
            }
        )
    )

    assert plan.steps[0].intent.value == intent


def test_invalid_template_is_rejected():
    with pytest.raises(PlanParsingError, match="does not match TaskPlan"):
        parse_task_plan(
            '{"task_id":"task_001","original_request":"Read report",'
            '"steps":[{"step_id":"step_001","agent":"file_agent",'
            '"operation":"READ","template":"ARBITRARY_POLICY"}]}'
        )
