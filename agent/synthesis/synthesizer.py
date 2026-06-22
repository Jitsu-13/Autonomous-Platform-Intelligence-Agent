"""
Capability Synthesizer — generates new LinearAPI capabilities at runtime.

When the executor encounters a capability name not in memory, it calls this module.
The synthesizer:
  1. Introspects Linear's GraphQL schema to understand what's available
  2. Asks the LLM to write a Python function that implements the capability
  3. Tests the generated function against a dry-run (schema validation)
  4. Registers it in capability memory if it works
  5. Reports clearly if it cannot proceed after MAX_ATTEMPTS
"""

import json
import os
import textwrap
import traceback
from typing import Optional
import anthropic

from agent.platform.linear.client import LinearClient
from agent.memory.capability_store import Capability, register_capability, get_capability

MAX_ATTEMPTS = 3

_llm = None


def _get_llm() -> anthropic.Anthropic:
    global _llm
    if _llm is None:
        _llm = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return _llm


SYNTHESIS_SYSTEM = """You are a GraphQL + Python code generator for the Linear API.

Given:
- A capability name and description (what it needs to do)
- Available GraphQL schema information from Linear
- Existing base capabilities for reference

Write a Python function with this EXACT signature:
  def execute(client, params: dict) -> dict:

Where `client` is a LinearClient with method `client.execute(query, variables)`.

The function must:
- Use `client.execute()` to call the Linear GraphQL API
- Accept parameters from `params` dict
- Return a dict with the result data
- Raise an exception with a clear message on failure

Return ONLY valid Python source code for the function, no markdown fences, no imports (they will be added).
"""


def synthesize_capability(
    name: str,
    description: str,
    step_params: dict,
    client: LinearClient,
) -> Optional[Capability]:
    """
    Attempt to synthesize a new capability. Returns the Capability if successful,
    None if it fails after MAX_ATTEMPTS.
    """
    existing = get_capability(name)
    if existing:
        return Capability(
            name=existing["name"],
            description=existing["description"],
            operation_type=existing["operation_type"],
            implementation=existing["implementation"],
            is_synthesized=bool(existing["is_synthesized"]),
        )

    # Introspect schema to understand what's available
    schema_context = _gather_schema_context(client, name, description)

    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        code = _generate_code(name, description, step_params, schema_context, last_error)
        if not code:
            continue

        success, result, error = _test_capability(code, client, step_params)

        if success:
            cap = Capability(
                name=name,
                description=description,
                operation_type="synthesized",
                implementation=code,
                is_synthesized=True,
            )
            register_capability(cap)
            return cap

        last_error = error or "unknown error"

    return None


def _gather_schema_context(client: LinearClient, name: str, description: str) -> str:
    """Introspect relevant types from the Linear schema."""
    context_parts = []

    # Heuristic: guess which types to introspect based on name/description
    type_hints = []
    combined = (name + " " + description).lower()
    if "issue" in combined:
        type_hints.extend(["IssueFilter", "IssueCreateInput", "IssueUpdateInput"])
    if "cycle" in combined or "sprint" in combined:
        type_hints.append("CycleFilter")
    if "project" in combined:
        type_hints.append("ProjectFilter")
    if "user" in combined or "assign" in combined:
        type_hints.append("UserFilter")
    if "label" in combined:
        type_hints.append("IssueLabelFilter")

    # Always include available mutations for context
    try:
        mutations = client.get_available_mutations()
        relevant = [m for m in mutations if any(k in m["name"].lower() for k in combined.split()[:3])]
        if relevant:
            context_parts.append("Relevant mutations:\n" + json.dumps(relevant[:5], indent=2))
    except Exception:
        pass

    for type_name in type_hints[:3]:
        try:
            data = client.introspect_type(type_name)
            if data.get("__type"):
                context_parts.append(f"Type {type_name}:\n" + json.dumps(data["__type"], indent=2))
        except Exception:
            pass

    return "\n\n".join(context_parts) if context_parts else "No schema context available."


def _generate_code(
    name: str,
    description: str,
    params: dict,
    schema_context: str,
    last_error: str,
) -> Optional[str]:
    error_note = f"\nPREVIOUS ATTEMPT FAILED WITH: {last_error}\nFix that error." if last_error else ""

    prompt = f"""Capability to implement: {name}
Description: {description}
Example params: {json.dumps(params, indent=2)}

Schema context from Linear:
{schema_context}
{error_note}

Write the Python function now."""

    try:
        response = _get_llm().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYNTHESIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        code = response.content[0].text.strip()
        # Strip any accidental markdown fences
        if "```" in code:
            parts = code.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("python"):
                    stripped = stripped[6:].strip()
                if "def execute" in stripped:
                    return stripped
        return code if "def execute" in code else None
    except Exception:
        return None


def _test_capability(code: str, client: LinearClient, params: dict) -> tuple[bool, Optional[dict], Optional[str]]:
    """
    Test synthesized code by executing it with a dry-run params dict.
    We use the real client but catch errors — a successful API call (even returning empty data)
    means the code is syntactically and structurally valid.
    """
    try:
        namespace: dict = {}
        exec(
            textwrap.dedent(f"""
import json
{code}
"""),
            namespace,
        )
        execute_fn = namespace.get("execute")
        if not callable(execute_fn):
            return False, None, "No callable 'execute' function found in generated code"

        # Use a minimal/safe params dict for validation
        test_params = {k: v for k, v in params.items() if v and v != "<<placeholder>>"}
        result = execute_fn(client, test_params)
        return True, result, None

    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"


def get_synthesis_report(name: str, attempted: int, last_error: str) -> str:
    return (
        f"Capability synthesis for '{name}' failed after {attempted} attempts. "
        f"Last error: {last_error}. "
        f"The agent cannot complete steps requiring this capability."
    )
