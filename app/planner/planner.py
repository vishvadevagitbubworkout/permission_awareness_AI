import json

from app.planner.ollama_client import OllamaClient
from app.planner.parsing import PlanParsingError, parse_task_plan
from app.planner.prompts import build_planner_prompt
from app.planner.schemas import PlanStep, PlannerIntent, TaskPlan

_ALLOWED_INTENTS = {
    "LIST",
    "READ",
    "MOVE",
    "RENAME",
    "CREATE",
    "WRITE",
    "DELETE",
    "BROWSER_OPEN",
    "EMAIL_DRAFT",
    "EMAIL_SEND",
    "ASK_CLARIFICATION",
}

_FILE_TEMPLATE_CONTRACTS = {
    "FILE_LIST": ("LIST", "LIST", "file_manager", "list"),
    "FILE_READ": ("READ", "READ", "file_manager", "read"),
    "FILE_MOVE": ("MOVE", "MOVE", "file_manager", "move"),
    "FILE_RENAME": ("RENAME", "RENAME", "file_manager", "rename"),
    "FILE_CREATE": ("CREATE", "CREATE", "file_manager", "create"),
    "FILE_WRITE": ("WRITE", "WRITE", "file_manager", "write"),
    "FILE_DELETE": ("DELETE", "DELETE", "file_manager", "delete"),
}


class Planner:
	""""Coordinate local model planning without executing the resulting plan."""

	def __init__(self, ollama_client: OllamaClient | None = None):
		self.ollama_client = ollama_client or OllamaClient()

	def _unsupported_intent_clarification(
		self, user_request: str, unsupported_intent: str
	) -> TaskPlan:
		return TaskPlan(
			task_id="task_001",
			original_request=user_request,
			steps=[
				PlanStep(
					step_id="step_001",
					agent="planner_agent",
					operation="CLARIFY",
					resource=None,
					parameters={
						"unsupported_intent": unsupported_intent,
						"reason": (
							"The requested action is outside the planner's supported intent vocabulary."
						),
					},
					intent=PlannerIntent.ASK_CLARIFICATION,
					template=None,
					description=(
						f"This is an unsupported intent: '{unsupported_intent}'. The requested operation is not currently supported by the planner's allowed intent vocabulary. "
						"Clarification is required before any action is considered."
					),
					confidence=0.0,
				)
			],
		)

	def _detect_unsupported_intent(self, raw_response: str) -> str | None:
		if not isinstance(raw_response, str) or not raw_response.strip():
			return None
		try:
			payload = json.loads(raw_response)
		except json.JSONDecodeError:
			return None
		if not isinstance(payload, dict):
			return None
		for step in payload.get("steps", []):
			if not isinstance(step, dict):
				continue
			intent = step.get("intent")
			if isinstance(intent, str) and intent not in _ALLOWED_INTENTS:
				return intent
		return None

	def create_plan(self, user_request: str) -> TaskPlan:
		if not isinstance(user_request, str) or not user_request.strip():
			raise ValueError("The user request must not be empty.")

		prompt = build_planner_prompt(user_request)
		raw_response = self.ollama_client.generate(prompt)
		try:
			plan = parse_task_plan(raw_response, require_proposal_fields=True)
			if plan.original_request != user_request:
				raise PlanParsingError(
					"The planning response changed the original user request."
				)
			return self._normalize_file_template_proposals(plan)
		except PlanParsingError as error:
			unsupported_intent = self._detect_unsupported_intent(raw_response)
			if unsupported_intent is not None:
				return self._unsupported_intent_clarification(user_request, unsupported_intent)
			raise

	@staticmethod
	def _normalize_file_template_proposals(plan: TaskPlan) -> TaskPlan:
		"""Convert a declared M1 file template into its fixed M3 contract.

		The model may describe an operation in prose (for example, "create a
		PDF").  It may not choose M3's agent, canonical operation, or fixed
		security parameters.  A mismatched intent/template remains untouched and
		is rejected later by M2/M3.
		"""
		for step in plan.steps:
			if step.template is None:
				continue
			contract = _FILE_TEMPLATE_CONTRACTS.get(step.template.value)
			if contract is None or step.intent is None:
				continue
			operation, intent, agent, mode = contract
			if step.intent.value != intent:
				continue
			if operation.lower() not in step.operation.lower():
				continue
			step.operation = operation
			step.agent = agent
			step.parameters = {"mode": mode}
		return plan
