"""
Executor: runs planned steps against Linear, handles partial failures,
resolves placeholders from prior step outputs, and produces StepResult records.
"""

import time
import json
import re
from typing import Any, Optional

from agent.core.models import PlannedStep, StepResult
from agent.memory.capability_store import get_capability, record_capability_use
from agent.platform.linear.client import LinearClient, LinearAPIError
from agent.synthesis.synthesizer import synthesize_capability


class ExecutorContext:
    """Accumulates outputs from completed steps so later steps can reference them."""

    def __init__(self):
        self._outputs: dict[int, dict] = {}

    def store(self, step_index: int, data: dict) -> None:
        self._outputs[step_index] = data

    def resolve(self, params: dict) -> dict:
        """Replace <<placeholder>> strings with values from prior step outputs."""
        return {k: self._resolve_value(v) for k, v in params.items()}

    def _resolve_value(self, val: Any) -> Any:
        if isinstance(val, str):
            return self._resolve_string(val)
        if isinstance(val, dict):
            return {k: self._resolve_value(v) for k, v in val.items()}
        if isinstance(val, list):
            return [self._resolve_value(v) for v in val]
        return val

    def _resolve_string(self, val: str) -> Any:
        # <<step_N.path.to.value>> syntax
        pattern = r"<<step_(\d+)\.([^>]+)>>"
        match = re.search(pattern, val)
        if match:
            step_idx = int(match.group(1))
            path = match.group(2).split(".")
            data = self._outputs.get(step_idx, {})
            for key in path:
                if isinstance(data, dict):
                    data = data.get(key)
                elif isinstance(data, list) and key.isdigit():
                    data = data[int(key)]
                else:
                    data = None
                if data is None:
                    break
            if data is not None:
                return data
        return val

    def get_all(self) -> dict:
        return dict(self._outputs)


def execute_step(
    step: PlannedStep,
    client: LinearClient,
    ctx: ExecutorContext,
) -> StepResult:
    start = time.time()
    prior_calls = client.call_count
    resolved_params = ctx.resolve(step.params)

    # 1. Look up capability in memory
    cap_data = get_capability(step.capability)

    # 2. If not found, attempt synthesis
    synthesized_name = None
    if cap_data is None:
        cap = synthesize_capability(step.capability, step.description, resolved_params, client)
        if cap is None:
            duration = int((time.time() - start) * 1000)
            return StepResult(
                step_index=step.step_index,
                capability=step.capability,
                description=step.description,
                outcome="failure",
                error=f"Capability '{step.capability}' not found and synthesis failed.",
                api_calls=client.call_count - prior_calls,
                duration_ms=duration,
            )
        cap_data = {
            "name": cap.name,
            "operation_type": cap.operation_type,
            "implementation": cap.implementation,
        }
        synthesized_name = cap.name

    # 3. Execute the capability
    try:
        result = _run_capability(cap_data, resolved_params, client)
        duration = int((time.time() - start) * 1000)
        calls = client.call_count - prior_calls
        record_capability_use(step.capability, success=True, duration_ms=duration)
        ctx.store(step.step_index, result)

        sr = StepResult(
            step_index=step.step_index,
            capability=step.capability,
            description=step.description,
            outcome="success",
            data=result,
            api_calls=calls,
            duration_ms=duration,
        )
        if synthesized_name:
            sr.data = sr.data or {}
            sr.data["_synthesized_capability"] = synthesized_name
        return sr

    except LinearAPIError as e:
        duration = int((time.time() - start) * 1000)
        calls = client.call_count - prior_calls
        record_capability_use(step.capability, success=False, duration_ms=duration)
        return StepResult(
            step_index=step.step_index,
            capability=step.capability,
            description=step.description,
            outcome="failure",
            error=str(e),
            api_calls=calls,
            duration_ms=duration,
        )

    except Exception as e:
        duration = int((time.time() - start) * 1000)
        record_capability_use(step.capability, success=False, duration_ms=duration)
        return StepResult(
            step_index=step.step_index,
            capability=step.capability,
            description=step.description,
            outcome="failure",
            error=f"Unexpected error: {type(e).__name__}: {e}",
            api_calls=client.call_count - prior_calls,
            duration_ms=duration,
        )


def _run_capability(cap_data: dict, params: dict, client: LinearClient) -> dict:
    op_type = cap_data["operation_type"]
    impl = cap_data["implementation"]

    if op_type in ("graphql_query", "graphql_mutation"):
        variables = params if params else None
        return client.execute(impl, variables)

    elif op_type in ("synthesized", "composite"):
        # Synthesized capabilities are stored as Python source
        namespace: dict = {}
        exec(f"import json\n{impl}", namespace)
        fn = namespace.get("execute")
        if not callable(fn):
            raise RuntimeError(f"Synthesized capability '{cap_data['name']}' has no execute() function")
        result = fn(client, params)
        return result if isinstance(result, dict) else {"result": result}

    else:
        raise RuntimeError(f"Unknown operation_type: {op_type}")
