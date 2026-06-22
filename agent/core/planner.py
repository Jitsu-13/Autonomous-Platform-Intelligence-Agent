"""
Planner: converts a natural language instruction into an ExecutionPlan.
Pulls memory context (past executions, capability success rates) so the plan
changes based on what the agent has learned.
"""

import json
import os
from anthropic import Anthropic

from agent.memory.manager import get_planner_context
from agent.memory.execution_store import get_run_count_for_intent
from agent.core.models import ExecutionPlan, PlannedStep

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return _client


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

    capabilities_text = json.dumps(ctx["available_capabilities"], indent=2)
    past_text = json.dumps(ctx["similar_past_executions"], indent=2)
    risky_text = json.dumps(ctx["risky_operations"], indent=2)

    user_message = f"""INSTRUCTION: {instruction}

RUN COUNT FOR SIMILAR INSTRUCTIONS: {run_count}

AVAILABLE CAPABILITIES ({ctx['total_capabilities']} total, {ctx['synthesized_capabilities']} synthesized):
{capabilities_text}

PAST SIMILAR EXECUTIONS:
{past_text}

RISKY OPERATIONS (high failure rate):
{risky_text}

Produce the execution plan JSON."""

    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)
    tokens = response.usage.input_tokens + response.usage.output_tokens

    steps = [PlannedStep(**s) for s in data["steps"]]

    return ExecutionPlan(
        instruction=instruction,
        intent_summary=data["intent_summary"],
        steps=steps,
        confidence=data.get("confidence", 1.0),
        memory_used=data.get("memory_used", False),
        memory_insights=data.get("memory_insights", []),
    ), tokens


def _hash_instruction(instruction: str) -> str:
    import hashlib
    normalised = " ".join(instruction.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]
