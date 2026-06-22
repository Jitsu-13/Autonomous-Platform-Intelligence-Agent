"""
Orchestrator: the main agent loop.

Flow:
  1. Pull memory context (past executions, capabilities, learned constraints)
  2. Plan: decompose instruction → ExecutionPlan
  3. Execute: run each step, handle failures, synthesize missing capabilities
  4. Learn: extract learnings, update metrics, persist to memory
  5. Report: return structured ExecutionReport
"""

import time
import uuid
from typing import Optional

from agent.core.models import ExecutionPlan, ExecutionReport, StepResult
from agent.core.planner import build_plan
from agent.core.executor import execute_step, ExecutorContext
from agent.memory.execution_store import ExecutionRecord, StepRecord, save_execution
from agent.memory.manager import boot, get_planner_context
from agent.learning.feedback import record_and_learn
from agent.platform.linear.client import LinearClient


def run(instruction: str, verbose: bool = False) -> ExecutionReport:
    """Entry point: run the agent on a single instruction."""
    boot()

    client = LinearClient()
    run_id = str(uuid.uuid4())
    start_time = time.time()
    total_tokens = 0

    if verbose:
        print(f"\n[Agent] Planning: {instruction!r}")

    # --- PLAN ---
    plan, plan_tokens = build_plan(instruction)
    total_tokens += plan_tokens

    if verbose:
        print(f"[Agent] Plan: {plan.intent_summary} ({len(plan.steps)} steps, confidence={plan.confidence:.0%})")
        if plan.memory_insights:
            for insight in plan.memory_insights:
                print(f"  [Memory] {insight}")

    # --- EXECUTE ---
    ctx = ExecutorContext()
    step_results: list[StepResult] = []
    synthesized_caps: list[str] = []
    aborted = False

    for step in plan.steps:
        if verbose:
            print(f"  [Step {step.step_index}] {step.description} (capability: {step.capability})")

        # Check if this step's dependencies all succeeded
        dep_failed = [
            d for d in step.depends_on
            if any(r.step_index == d and r.outcome == "failure" for r in step_results)
        ]
        if dep_failed:
            step_results.append(StepResult(
                step_index=step.step_index,
                capability=step.capability,
                description=step.description,
                outcome="skipped",
                error=f"Skipped: dependency steps {dep_failed} failed",
            ))
            if not step.is_optional:
                aborted = True
            if verbose:
                print(f"    -> SKIPPED (dependency failed)")
            continue

        result = execute_step(step, client, ctx)
        step_results.append(result)

        # Track synthesized capabilities
        if result.data and result.data.get("_synthesized_capability"):
            synthesized_caps.append(result.data["_synthesized_capability"])

        if verbose:
            if result.outcome == "success":
                print(f"    -> OK ({result.api_calls} API calls, {result.duration_ms}ms)")
            else:
                print(f"    -> FAILED: {result.error}")

        # Non-optional failure: abort remaining non-optional steps
        if result.outcome == "failure" and not step.is_optional:
            # Mark subsequent non-optional steps as skipped
            remaining_indices = {s.step_index for s in plan.steps if s.step_index > step.step_index}
            for future_step in plan.steps:
                if future_step.step_index in remaining_indices and not future_step.is_optional:
                    step_results.append(StepResult(
                        step_index=future_step.step_index,
                        capability=future_step.capability,
                        description=future_step.description,
                        outcome="skipped",
                        error=f"Skipped: prior required step {step.step_index} failed",
                    ))
            aborted = True
            break

    # --- DETERMINE OUTCOME ---
    total_duration = int((time.time() - start_time) * 1000)
    succeeded = sum(1 for r in step_results if r.outcome == "success")
    failed = sum(1 for r in step_results if r.outcome == "failure")
    skipped = sum(1 for r in step_results if r.outcome == "skipped")

    if failed == 0:
        overall = "success"
    elif succeeded == 0:
        overall = "failure"
    else:
        overall = "partial"

    # --- PERSIST TO MEMORY ---
    exec_record = ExecutionRecord(
        run_id=run_id,
        instruction=instruction,
        steps=[
            StepRecord(
                operation=r.capability,
                params={},
                outcome=r.outcome,
                result=r.data,
                error=r.error,
                api_calls=r.api_calls,
                duration_ms=r.duration_ms,
            )
            for r in step_results
        ],
        outcome=overall,
        api_calls=client.call_count,
        duration_ms=total_duration,
        tokens_used=total_tokens,
        error=_first_error(step_results) if overall != "success" else None,
    )
    save_execution(exec_record)

    # --- LEARN ---
    report = ExecutionReport(
        run_id=run_id,
        instruction=instruction,
        overall_outcome=overall,
        steps_total=len(plan.steps),
        steps_succeeded=succeeded,
        steps_failed=failed,
        steps_skipped=skipped,
        step_results=step_results,
        api_calls_total=client.call_count,
        duration_ms=total_duration,
        tokens_used=total_tokens,
        memory_applied=plan.memory_insights,
        synthesized_capabilities=synthesized_caps,
        error_summary=_first_error(step_results) if overall != "success" else None,
    )

    learnings = record_and_learn(report)
    report.learnings_extracted = learnings

    return report


def _first_error(results: list[StepResult]) -> Optional[str]:
    for r in results:
        if r.outcome == "failure" and r.error:
            return r.error[:300]
    return None
