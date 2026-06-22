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

You will receive:
- The instruction
- Available capabilities (name, description, success rates)
- Past similar executions (what worked, what failed, how many API calls)
- Risky operations (operations with high failure rates)

RULES:
1. Only use capabilities from the provided list. If a step requires something not in the list,
   name it anyway — the synthesizer will try to build it.
2. Prefer capabilities with high success rates. Avoid operations flagged as risky unless necessary.
3. If memory shows a similar past execution that failed, adjust your approach.
4. If memory shows a similar past execution that succeeded with fewer steps, use that ordering.
5. Mark steps as optional (is_optional: true) if they are enrichment steps that should not block
   the rest of the plan on failure.
6. Set confidence (0.0–1.0) based on how well the available capabilities cover this instruction.
7. In memory_insights, list any adjustments you made because of past execution data.

OUTPUT FORMAT (JSON only, no prose):
{
  "intent_summary": "brief description of what the agent will accomplish",
  "confidence": 0.95,
  "memory_used": true,
  "memory_insights": ["skipping X because it failed in 3 prior runs", "..."],
  "steps": [
    {
      "step_index": 0,
      "capability": "capability_name",
      "description": "What this step does in plain English",
      "params": { "key": "value or <<placeholder>>" },
      "depends_on": [],
      "is_optional": false
    }
  ]
}

Use <<placeholder>> for values that will be resolved at execution time (e.g. team IDs fetched in prior steps).
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
