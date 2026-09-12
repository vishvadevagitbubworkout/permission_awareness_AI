import json

import pytest

from app.planner.planner import Planner
from app.planner.schemas import PlannerIntent, TaskPlan


class FakeOllamaClient:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if self.response.startswith("{"):
            payload = json.loads(self.response)
            for step in payload.get("steps", []):
                operation = step.get("operation", "")
                step.setdefault("template", "FILE_READ")
                step.setdefault("intent", "READ")
                step.setdefault("opaque_file_refs", [])
                step.setdefault("parameters", {})
                step.setdefault("description", operation or "planned action")
                step.setdefault("confidence", 1.0)
            self.response = json.dumps(payload)
        return self.response


def test_planner_coordinates_prompt_model_and_validation():
    response = json.dumps(
        {
            "task_id": "task_001",
            "original_request": "Read report.pdf from Documents",
            "steps": [
                {
                    "step_id": "step_001",
                    "agent": "file_agent",
                    "operation": "READ",
                    "resource": "report.pdf",
                    "parameters": {"location": "Documents"},
                }
            ],
        }
    )
    client = FakeOllamaClient(response)

    plan = Planner(client).create_plan("Read report.pdf from Documents")

    assert isinstance(plan, TaskPlan)
    assert plan.steps[0].agent == "file_manager"
    assert len(client.prompts) == 1
    assert "Read report.pdf from Documents" in client.prompts[0]


def test_planner_rejects_empty_user_request():
    with pytest.raises(ValueError, match="must not be empty"):
        Planner(FakeOllamaClient("unused")).create_plan("  ")


def make_planner(response):
    return Planner(FakeOllamaClient(json.dumps(response)))


def test_planner_identifies_simple_file_task():
    planner = make_planner(
        {
            "task_id": "task_001",
            "original_request": "Read report.pdf from Documents.",
            "steps": [
                {
                    "step_id": "step_001",
                    "agent": "file_agent",
                    "operation": "READ",
                    "resource": "report.pdf",
                    "parameters": {"location": "Documents"},
                }
            ],
        }
    )

    plan = planner.create_plan("Read report.pdf from Documents.")

    assert plan.steps[0].agent == "file_manager"
    assert plan.steps[0].operation == "READ"


def test_planner_normalizes_a_file_template_to_the_m3_contract():
    planner = make_planner({
        "task_id": "task_001", "original_request": "Create report.pdf in Documents.",
        "steps": [{"step_id": "step_001", "agent": "user",
                   "operation": "create report.pdf", "resource": "Documents",
                   "template": "FILE_CREATE", "intent": "CREATE", "parameters": {}}],
    })
    plan = planner.create_plan("Create report.pdf in Documents.")
    assert (plan.steps[0].agent, plan.steps[0].operation, plan.steps[0].parameters) == (
        "file_manager", "CREATE", {"mode": "create"}
    )


def test_planner_identifies_multiple_logical_actions():
    planner = make_planner(
        {
            "task_id": "task_001",
            "original_request": "Read report.pdf and summarize it.",
            "steps": [
                {
                    "step_id": "step_001",
                    "agent": "file_agent",
                    "operation": "READ",
                    "resource": "report.pdf",
                    "parameters": {},
                },
                {
                    "step_id": "step_002",
                    "agent": "summarization_agent",
                    "operation": "SUMMARIZE",
                    "resource": "report.pdf",
                    "parameters": {},
                },
            ],
        }
    )

    plan = planner.create_plan("Read report.pdf and summarize it.")

    assert len(plan.steps) == 2
    assert [step.operation for step in plan.steps] == ["READ", "SUMMARIZE"]


def test_planner_identifies_browser_task():
    planner = make_planner(
        {
            "task_id": "task_001",
            "original_request": "Open the university website and search for exam results.",
            "steps": [
                {
                    "step_id": "step_001",
                    "agent": "browser_agent",
                    "operation": "OPEN",
                    "resource": "university website",
                    "parameters": {},
                },
                {
                    "step_id": "step_002",
                    "agent": "browser_agent",
                    "operation": "SEARCH",
                    "resource": "exam results",
                    "parameters": {},
                },
            ],
        }
    )

    plan = planner.create_plan(
        "Open the university website and search for exam results."
    )

    assert all(step.agent == "browser_agent" for step in plan.steps)
    assert [step.operation for step in plan.steps] == ["OPEN", "SEARCH"]


def test_planner_identifies_email_task():
    planner = make_planner(
        {
            "task_id": "task_001",
            "original_request": "Send an email saying the meeting is postponed.",
            "steps": [
                {
                    "step_id": "step_001",
                    "agent": "email_agent",
                    "operation": "SEND",
                    "resource": "email",
                    "parameters": {"body": "The meeting is postponed."},
                }
            ],
        }
    )

    plan = planner.create_plan("Send an email saying the meeting is postponed.")

    assert plan.steps[0].agent == "email_agent"
    assert plan.steps[0].operation == "SEND"


def test_planner_rejects_malformed_model_output():
    planner = Planner(FakeOllamaClient("not valid JSON"))

    with pytest.raises(ValueError, match="invalid JSON"):
        planner.create_plan("Read report.pdf")


def test_planner_rejects_model_replacing_original_request():
    planner = make_planner(
        {
            "task_id": "task_001",
            "original_request": "Read public.txt",
            "steps": [
                {
                    "step_id": "step_001",
                    "agent": "file_agent",
                    "operation": "READ",
                    "resource": "public.txt",
                    "parameters": {},
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="changed the original user request"):
        planner.create_plan("Delete secret.txt")


@pytest.mark.parametrize("unsupported_intent", ["COPY", "DOWNLOAD", "EXECUTE"])
def test_planner_routes_unsupported_intent_to_clarification(unsupported_intent, tmp_path):
    request = "create new file called sun.pdf in documents"
    response = json.dumps(
        {
            "task_id": "task_001",
            "original_request": request,
            "steps": [
                {
                    "step_id": "step_001",
                    "agent": "file_agent",
                    "operation": "WRITE",
                    "resource": "sun.pdf",
                    "intent": unsupported_intent,
                    "template": "FILE_READ",
                    "opaque_file_refs": [],
                    "parameters": {"location": "Documents"},
                    "description": "Create the requested file.",
                    "confidence": 0.95,
                }
            ],
        }
    )
    planner = Planner(FakeOllamaClient(response))

    plan = planner.create_plan(request)

    assert isinstance(plan, TaskPlan)
    assert plan.steps[0].intent == PlannerIntent.ASK_CLARIFICATION
    assert plan.steps[0].confidence == 0.0
    assert "unsupported" in plan.steps[0].description.lower()
    assert not (tmp_path / "sun.pdf").exists()


def test_planner_describes_deletion_without_executing_it(tmp_path):
    target = tmp_path / "important.txt"
    planner = make_planner(
        {
            "task_id": "task_001",
            "original_request": "Delete all files in my Documents folder.",
            "steps": [
                {
                    "step_id": "step_001",
                    "agent": "file_agent",
                    "operation": "DELETE",
                    "resource": "Documents",
                    "parameters": {"recursive": True},
                }
            ],
        }
    )

    plan = planner.create_plan("Delete all files in my Documents folder.")

    assert plan.steps[0].operation == "DELETE"
    assert not target.exists()
