"""Capability Memory — what the agent knows how to do, with success rates and constraints."""

import json
from dataclasses import dataclass, field
from typing import Optional
from .schema import get_connection


@dataclass
class Capability:
    name: str
    description: str
    operation_type: str          # graphql_query | graphql_mutation | composite | synthesized
    implementation: str          # Python source or GraphQL query string
    is_synthesized: bool = False
    constraints: list[str] = field(default_factory=list)


def register_capability(cap: Capability) -> None:
    """Insert or replace a capability (upsert by name)."""
    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO capabilities
               (name, description, operation_type, implementation, is_synthesized,
                constraints_json, synthesized_at)
               VALUES (?,?,?,?,?,?,CASE WHEN ? THEN datetime('now') ELSE NULL END)
               ON CONFLICT(name) DO UPDATE SET
                 description      = excluded.description,
                 implementation   = excluded.implementation,
                 constraints_json = excluded.constraints_json,
                 synthesized_at   = CASE WHEN excluded.is_synthesized
                                         THEN datetime('now')
                                         ELSE synthesized_at END""",
            (
                cap.name,
                cap.description,
                cap.operation_type,
                cap.implementation,
                int(cap.is_synthesized),
                json.dumps(cap.constraints) if cap.constraints else None,
                int(cap.is_synthesized),
            ),
        )
    conn.close()


def record_capability_use(name: str, success: bool, duration_ms: int) -> None:
    conn = get_connection()
    with conn:
        if success:
            conn.execute(
                """UPDATE capabilities SET
                     success_count   = success_count + 1,
                     avg_duration_ms = (avg_duration_ms * success_count + ?) / (success_count + 1),
                     last_used_at    = datetime('now')
                   WHERE name = ?""",
                (duration_ms, name),
            )
        else:
            conn.execute(
                "UPDATE capabilities SET failure_count = failure_count + 1 WHERE name = ?",
                (name,),
            )
    conn.close()


def add_constraint(capability_name: str, constraint_type: str, description: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """INSERT INTO discovered_constraints (capability, constraint_type, description)
               VALUES (?,?,?)""",
            (capability_name, constraint_type, description),
        )
    conn.close()


def get_capability(name: str) -> Optional[dict]:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM capabilities WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_capabilities() -> list[dict]:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM capabilities ORDER BY success_count DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_capability_summary() -> list[dict]:
    """Lightweight summary for injecting into planner context."""
    conn = get_connection()
    cur = conn.execute(
        """SELECT name, description, operation_type, is_synthesized,
                  success_count, failure_count,
                  ROUND(avg_duration_ms) as avg_ms
           FROM capabilities
           ORDER BY success_count DESC"""
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_constraints_for(capability_name: str) -> list[dict]:
    conn = get_connection()
    cur = conn.execute(
        "SELECT * FROM discovered_constraints WHERE capability = ?", (capability_name,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_intent_pattern(pattern: str, capability_name: str, success: bool) -> None:
    """Track which capabilities work for which instruction patterns."""
    conn = get_connection()
    with conn:
        existing = conn.execute(
            "SELECT * FROM intent_patterns WHERE pattern = ? AND capability_name = ?",
            (pattern, capability_name),
        ).fetchone()

        if existing:
            new_count = existing["sample_count"] + 1
            new_rate = (
                existing["success_rate"] * existing["sample_count"] + int(success)
            ) / new_count
            conn.execute(
                """UPDATE intent_patterns SET success_rate=?, sample_count=?, updated_at=datetime('now')
                   WHERE pattern=? AND capability_name=?""",
                (new_rate, new_count, pattern, capability_name),
            )
        else:
            conn.execute(
                """INSERT INTO intent_patterns (pattern, capability_name, success_rate)
                   VALUES (?,?,?)""",
                (pattern, capability_name, 1.0 if success else 0.0),
            )
    conn.close()


def get_best_capability_for_pattern(pattern: str) -> Optional[str]:
    """Return the capability name with highest success rate for a keyword pattern."""
    conn = get_connection()
    cur = conn.execute(
        """SELECT capability_name FROM intent_patterns
           WHERE pattern LIKE ? AND sample_count >= 2
           ORDER BY success_rate DESC, sample_count DESC
           LIMIT 1""",
        (f"%{pattern}%",),
    )
    row = cur.fetchone()
    conn.close()
    return row["capability_name"] if row else None
