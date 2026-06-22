"""Unified memory interface — init, compact, and surface context for the planner."""

import json
from .schema import init_schema, get_connection
from .execution_store import get_similar_executions, get_step_success_rates
from .capability_store import get_capability_summary, get_all_capabilities


def boot() -> None:
    """Call once at agent startup to ensure schema exists."""
    init_schema()
    _seed_base_capabilities()


def _seed_base_capabilities() -> None:
    from agent.platform.linear.base_ops import seed_capabilities
    seed_capabilities()


def get_planner_context(instruction: str) -> dict:
    """
    Returns a structured context dict the planner injects into its prompt.
    This is how memory actively changes behaviour — not just logging.
    """
    similar = get_similar_executions(instruction, limit=3)
    step_rates = get_step_success_rates()
    capabilities = get_capability_summary()

    # Build a concise "what worked / what failed" summary
    past_insights = []
    for ex in similar:
        steps = json.loads(ex["steps_json"])
        failed = [s["operation"] for s in steps if s["outcome"] == "failure"]
        succeeded = [s["operation"] for s in steps if s["outcome"] == "success"]
        past_insights.append({
            "instruction": ex["instruction"],
            "outcome": ex["outcome"],
            "api_calls": ex["api_calls"],
            "duration_ms": ex["duration_ms"],
            "succeeded_ops": succeeded,
            "failed_ops": failed,
        })

    # Highlight operations with high failure rates
    risky_ops = {
        op: data for op, data in step_rates.items()
        if data["failures"] > 0 and data["successes"] / max(data["successes"] + data["failures"], 1) < 0.7
    }

    return {
        "similar_past_executions": past_insights,
        "risky_operations": risky_ops,
        "available_capabilities": capabilities,
        "total_capabilities": len(capabilities),
        "synthesized_capabilities": sum(1 for c in capabilities if c["is_synthesized"]),
    }


def compact_old_executions(keep_recent: int = 50) -> int:
    """
    Memory compaction: summarise executions older than the most recent `keep_recent`
    by collapsing them into aggregated learnings. Returns number of rows compacted.
    """
    conn = get_connection()
    with conn:
        cur = conn.execute(
            "SELECT id FROM executions ORDER BY created_at DESC LIMIT ?", (keep_recent,)
        )
        keep_ids = [r[0] for r in cur.fetchall()]

        if not keep_ids:
            conn.close()
            return 0

        placeholders = ",".join("?" * len(keep_ids))
        cur = conn.execute(
            f"SELECT COUNT(*) FROM executions WHERE id NOT IN ({placeholders})", keep_ids
        )
        to_compact = cur.fetchone()[0]

        if to_compact == 0:
            conn.close()
            return 0

        # Aggregate stats from old executions before deleting
        cur = conn.execute(
            f"""SELECT operation,
                       SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) as s,
                       SUM(CASE WHEN outcome='failure' THEN 1 ELSE 0 END) as f
                FROM execution_steps
                WHERE run_id IN (
                    SELECT run_id FROM executions WHERE id NOT IN ({placeholders})
                )
                GROUP BY operation""",
            keep_ids,
        )
        for row in cur.fetchall():
            conn.execute(
                """UPDATE capabilities SET
                     success_count = success_count + ?,
                     failure_count = failure_count + ?
                   WHERE name = ?""",
                (row["s"], row["f"], row["operation"]),
            )

        # Delete old steps and executions
        conn.execute(
            f"""DELETE FROM execution_steps WHERE run_id IN (
                SELECT run_id FROM executions WHERE id NOT IN ({placeholders})
            )""",
            keep_ids,
        )
        conn.execute(
            f"DELETE FROM executions WHERE id NOT IN ({placeholders})", keep_ids
        )

    conn.close()
    return to_compact


def get_memory_stats() -> dict:
    conn = get_connection()
    stats = {}
    for table in ["executions", "capabilities", "execution_steps", "discovered_constraints"]:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cur.fetchone()[0]
    conn.close()
    return stats
