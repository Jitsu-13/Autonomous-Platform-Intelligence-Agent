"""
Planner: converts a natural language instruction into an ExecutionPlan.
Pulls memory context (past executions, capability success rates) so the plan
changes based on what the agent has learned.
"""

import json
import hashlib

from agent.llm.provider import complete
from agent.memory.manager import get_planner_context
from agent.memory.execution_store import get_run_count_for_intent
from agent.core.models import ExecutionPlan, PlannedStep


SYSTEM_PROMPT = """You are the Planner component of an Autonomous Linear Agent.

Your job is to decompose a natural language instruction into an ordered list of executable steps,
where each step maps to exactly one capability the agent has.

--- PLACEHOLDER SYNTAX ---
Reference output from a prior step with: <<stepN.path.to.value>>
where N is the step_index of the prior step.

EXACT PATHS FOR COMMON CAPABILITIES (replace N with actual step_index):
  get_teams                   team id:    <<stepN.teams.nodes.0.id>>
  get_label_by_name           label id:   <<stepN.issueLabels.nodes.0.id>>
  get_labels                  label id:   <<stepN.issueLabels.nodes.0.id>>
  get_state_by_type           state id:   <<stepN.workflowStates.nodes.0.id>>
  get_workflow_states         state id:   <<stepN.workflowStates.nodes.0.id>>
  get_cycles                  cycle id:   <<stepN.cycles.nodes.0.id>>
  get_users                   user id:    <<stepN.users.nodes.0.id>>
  create_issue                issue id:   <<stepN.issueCreate.issue.id>>
  create_issue                issue url:  <<stepN.issueCreate.issue.url>>
  get_unassigned_open_issues         issue id:   <<stepN.issues.nodes.0.id>>
  get_cycle_issues                   issue id:   <<stepN.issues.nodes.0.id>>
  get_backlog_issues                 issue id:   <<stepN.issues.nodes.0.id>>
  create_triage_summary_issue issues_data: <<stepN.issues.nodes>>  (pass entire array)
  create_triage_summary_issue result url:  <<stepN.issueCreate.issue.url>>

--- PRIORITY ENCODING (create_issue / update_issue) ---
priority MUST be an INTEGER. Never use strings like "high" or "urgent".
  0 = No priority, 1 = Urgent, 2 = High, 3 = Medium, 4 = Low

--- LABEL IDS ---
labelIds must be a JSON array: ["<<stepN.issueLabels.nodes.0.id>>"]
Always use get_label_by_name (params: name only, NO teamId) before create_issue
when you need a specific label. Use the label id from that step.

--- TEAM ID ---
Always start with get_teams to resolve teamId. Use <<step0.teams.nodes.0.id>>
for all subsequent steps that need teamId. Never hardcode a team ID.

--- PLANNING RULES ---
1. Only use capabilities from the provided list. If a step requires something not in the list,
   name it anyway -- the synthesizer will try to build it.
2. Prefer capabilities with high success rates. Avoid operations flagged as risky unless necessary.
3. If memory shows a similar past execution that failed, adjust your approach.
4. If memory shows a similar past execution that succeeded with fewer steps, use that ordering.
5. Mark steps as optional (is_optional: true) if they are enrichment steps that should not block
   the rest of the plan on failure.
6. Set confidence (0.0-1.0) based on how well the available capabilities cover this instruction.
7. In memory_insights, list any adjustments you made because of past execution data.
8. Every step that needs a teamId must reference it via placeholder from the get_teams step.
9. When instruction asks to "create a summary", "create a report", or "breakdown" of issues: use
   create_triage_summary_issue with issues_data=<<stepN.issues.nodes>> — NEVER use create_issue
   with a static description for this, as the description will be empty/incorrect.

--- OUTPUT FORMAT (JSON only, no prose) ---
{
  "intent_summary": "brief description of what the agent will accomplish",
  "confidence": 0.95,
  "memory_used": true,
  "memory_insights": ["skipping X because it failed in 3 prior runs"],
  "steps": [
    {
      "step_index": 0,
      "capability": "capability_name",
      "description": "What this step does in plain English",
      "params": { "key": "value or <<step0.path.to.value>>" },
      "depends_on": [],
      "is_optional": false
    }
  ]
}
"""


def build_plan(instruction: str) -> tuple[ExecutionPlan, int]:
    ctx = get_planner_context(instruction)
    run_count = get_run_count_for_intent(_hash_instruction(instruction))

    user_message = f"""INSTRUCTION: {instruction}

RUN COUNT FOR SIMILAR INSTRUCTIONS: {run_count}

AVAILABLE CAPABILITIES ({ctx['total_capabilities']} total, {ctx['synthesized_capabilities']} synthesized):
{json.dumps(ctx['available_capabilities'], indent=2)}

PAST SIMILAR EXECUTIONS:
{json.dumps(ctx['similar_past_executions'], indent=2)}

RISKY OPERATIONS (high failure rate):
{json.dumps(ctx['risky_operations'], indent=2)}

Produce the execution plan JSON."""

    response = complete(SYSTEM_PROMPT, user_message, max_tokens=2048, fast=False)

    raw = response.text
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)
    steps = [PlannedStep(**s) for s in data["steps"]]

    plan = ExecutionPlan(
        instruction=instruction,
        intent_summary=data["intent_summary"],
        steps=steps,
        confidence=data.get("confidence", 1.0),
        memory_used=data.get("memory_used", False),
        memory_insights=data.get("memory_insights", []),
    )
    return plan, response.tokens_used


def _hash_instruction(instruction: str) -> str:
    normalised = " ".join(instruction.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]
