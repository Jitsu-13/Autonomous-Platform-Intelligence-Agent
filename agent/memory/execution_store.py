"""Execution Memory — structured knowledge of what the agent has done before."""

import json
import uuid
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from .schema import get_connection


@dataclass
class StepRecord:
    operation: str
    params: dict
    outcome: str          # success | failure | skipped
    result: Optional[dict] = None
    error: Optional[str] = None
    api_calls: int = 0
    duration_ms: int = 0


@dataclass
class ExecutionRecord:
    instruction: str
    steps: list[StepRecord] = field(default_factory=list)
    outcome: str = "success"
    api_calls: int = 0
    duration_ms: int = 0
    tokens_used: int = 0
    error: Optional[str] = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def intent_hash(self) -> str:
        """Stable hash of normalised instruction for similarity lookups."""
        normalised = " ".join(self.instruction.lower().split())
        return hashlib.sha256(normalised.encode()).hexdigest()[:16]


def save_execution(record: ExecutionRecord) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO executions
               (run_id, instruction, intent_hash, steps_json, outcome,
                api_calls, duration_ms, tokens_used, error)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                record.run_id,
                record.instruction,
                record.intent_hash,
                json.dumps([s.__dict__ for s in record.steps]),
                record.outcome,
                record.api_calls,
                record.duration_ms,
                record.tokens_used,
                record.error,
            ),
        )
        for i, step in enumerate(record.steps):
            conn.execute(
                """INSERT INTO execution_steps
                   (run_id, step_index, operation, params_json, outcome,
                    result_json, error, api_calls, duration_ms)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    record.run_id,
                    i,
                    step.operation,
                    json.dumps(step.params),
                    step.outcome,
                    json.dumps(step.result) if step.result else None,
                    step.error,
                    step.api_calls,
                    step.duration_ms,
                ),
            )
    conn.close()


def save_learning(run_id: str, learning_type: str, subject: str, observation: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO execution_learnings (run_id, learning_type, subject, observation)
               VALUES (?,?,?,?)""",
            (run_id, learning_type, subject, observation),
        )
    conn.close()


def get_similar_executions(instruction: str, limit: int = 5) -> list[dict]:
    """Return past executions whose intent_hash or keyword overlap is highest."""
    normalised = " ".join(instruction.lower().split())
    intent_hash = hashlib.sha256(normalised.encode()).hexdigest()[:16]

    keywords = [w for w in normalised.split() if len(w) > 4]

    conn = get_connection()
    rows = []

    # Exact hash match first
    cur = conn.execute(
        "SELECT * FROM executions WHERE intent_hash = ? ORDER BY created_at DESC LIMIT ?",
        (intent_hash, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]

    # Keyword fallback
    if not rows and keywords:
        like_clauses = " OR ".join(["instruction LIKE ?" for _ in keywords[:5]])
        params = [f"%{k}%" for k in keywords[:5]] + [limit]
        cur = conn.execute(
            f"SELECT * FROM executions WHERE {like_clauses} ORDER BY created_at DESC LIMIT ?",
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]

    conn.close()
    return rows


def get_step_success_rates() -> dict[str, dict]:
    """Return success/failure counts per operation type across all executions."""
    conn = get_connection()
    cur = conn.execute(
        """SELECT operation,
                  SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) as successes,
                  SUM(CASE WHEN outcome='failure' THEN 1 ELSE 0 END) as failures,
                  AVG(duration_ms) as avg_ms
           FROM execution_steps
           GROUP BY operation"""
    )
    result = {}
    for row in cur.fetchall():
        result[row["operation"]] = {
            "successes": row["successes"],
            "failures": row["failures"],
            "avg_ms": row["avg_ms"],
        }
    conn.close()
    return result


def get_run_count_for_intent(intent_hash: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "SELECT COUNT(*) FROM executions WHERE intent_hash = ?", (intent_hash,)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count
