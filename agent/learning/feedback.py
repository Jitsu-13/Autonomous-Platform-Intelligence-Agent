"""
Self-learning feedback loop.

After each execution, this module:
1. Records task metrics (api_calls, duration) keyed by intent_hash + run_number
2. Extracts structured learnings from step outcomes
3. Updates capability success rates and intent patterns
4. Surfaces a measurable improvement comparison (run N vs run 1)
"""

import json
import hashlib
from agent.memory.schema import get_connection
from agent.memory.execution_store import save_learning, get_run_count_for_intent
from agent.memory.capability_store import update_intent_pattern
from agent.core.models import ExecutionReport, StepResult


def record_and_learn(report: ExecutionReport) -> list[str]:
    """
    Process an execution report, extract learnings, update metrics.
    Returns a list of human-readable learning statements.
    """
    intent_hash = _hash_instruction(report.instruction)
    run_number = get_run_count_for_intent(intent_hash)

    _record_task_metrics(
        intent_hash=intent_hash,
        task_label=report.instruction[:80],
        run_number=run_number,
        api_calls=report.api_calls_total,
        duration_ms=report.duration_ms,
        outcome=report.overall_outcome,
        optimizations=report.memory_applied,
    )

    learnings = []

    # Extract learnings from each failed step
    for step in report.step_results:
        if step.outcome == "failure" and step.error:
            observation = f"Step '{step.capability}' failed: {step.error[:200]}"
            save_learning(report.run_id, "step_failure", step.capability, observation)
            learnings.append(f"Learned: {observation}")

            # Update intent pattern with failure
            keywords = _extract_keywords(report.instruction)
            for kw in keywords:
                update_intent_pattern(kw, step.capability, success=False)

        elif step.outcome == "success":
            keywords = _extract_keywords(report.instruction)
            for kw in keywords:
                update_intent_pattern(kw, step.capability, success=True)

    # Learning from ordering: if partial failure, record which step index caused it
    if report.overall_outcome == "partial":
        failed_indices = [s.step_index for s in report.step_results if s.outcome == "failure"]
        save_learning(
            report.run_id,
            "partial_failure_pattern",
            report.instruction[:80],
            f"Failed at step indices: {failed_indices}",
        )
        learnings.append(f"Recorded partial failure pattern at steps {failed_indices}")

    # Learning from API call efficiency
    if run_number > 1:
        improvement = _check_improvement(intent_hash, report.api_calls_total, run_number)
        if improvement:
            learnings.append(improvement)
            save_learning(report.run_id, "efficiency_improvement", "api_calls", improvement)

    return learnings


def get_improvement_report(instruction: str) -> dict:
    """
    Returns a before/after comparison for a given instruction type.
    The key artifact for the demo's measurable learning signal.
    """
    intent_hash = _hash_instruction(instruction)
    conn = get_connection()

    cur = conn.execute(
        """SELECT run_number, api_calls, duration_ms, outcome, optimizations
           FROM task_metrics
           WHERE intent_hash = ?
           ORDER BY run_number ASC""",
        (intent_hash,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if len(rows) < 2:
        return {"message": "Not enough runs yet to show improvement", "runs": rows}

    first = rows[0]
    latest = rows[-1]

    api_delta = first["api_calls"] - latest["api_calls"]
    time_delta = first["duration_ms"] - latest["duration_ms"]

    return {
        "instruction_type": instruction[:80],
        "total_runs": len(rows),
        "first_run": {
            "api_calls": first["api_calls"],
            "duration_ms": first["duration_ms"],
            "outcome": first["outcome"],
        },
        "latest_run": {
            "api_calls": latest["api_calls"],
            "duration_ms": latest["duration_ms"],
            "outcome": latest["outcome"],
        },
        "api_calls_saved": api_delta,
        "time_saved_ms": time_delta,
        "improvement_pct": round((api_delta / max(first["api_calls"], 1)) * 100, 1),
        "all_runs": rows,
    }


def _record_task_metrics(
    intent_hash: str,
    task_label: str,
    run_number: int,
    api_calls: int,
    duration_ms: int,
    outcome: str,
    optimizations: list[str],
) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO task_metrics
               (intent_hash, task_label, run_number, api_calls, duration_ms, outcome, optimizations)
               VALUES (?,?,?,?,?,?,?)""",
            (
                intent_hash,
                task_label,
                run_number,
                api_calls,
                duration_ms,
                outcome,
                json.dumps(optimizations) if optimizations else None,
            ),
        )
    conn.close()


def _check_improvement(intent_hash: str, current_calls: int, run_number: int) -> str:
    conn = get_connection()
    cur = conn.execute(
        "SELECT api_calls FROM task_metrics WHERE intent_hash = ? ORDER BY run_number ASC LIMIT 1",
        (intent_hash,),
    )
    row = cur.fetchone()
    conn.close()

    if row and row[0] > current_calls:
        saved = row[0] - current_calls
        pct = round(saved / row[0] * 100)
        return (
            f"Run {run_number}: {current_calls} API calls vs {row[0]} on run 1 "
            f"({saved} fewer, {pct}% improvement)"
        )
    return ""


def _hash_instruction(instruction: str) -> str:
    normalised = " ".join(instruction.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


def _extract_keywords(instruction: str) -> list[str]:
    stop = {"the", "a", "an", "and", "or", "for", "to", "in", "of", "all", "with"}
    words = instruction.lower().split()
    return [w for w in words if len(w) > 4 and w not in stop][:5]
