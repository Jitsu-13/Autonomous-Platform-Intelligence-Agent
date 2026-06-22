"""SQLite schema and connection management for the two-layer memory system."""

import sqlite3
import os
from pathlib import Path


def get_db_path() -> str:
    return os.getenv("MEMORY_DB_PATH", "./memory.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    conn = get_connection()
    with conn:
        # --- Execution Memory ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT    NOT NULL UNIQUE,
                instruction TEXT    NOT NULL,
                intent_hash TEXT    NOT NULL,
                steps_json  TEXT    NOT NULL,
                outcome     TEXT    NOT NULL CHECK(outcome IN ('success','partial','failure')),
                api_calls   INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                error       TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Each step within an execution
        conn.execute("""
            CREATE TABLE IF NOT EXISTS execution_steps (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       TEXT    NOT NULL REFERENCES executions(run_id),
                step_index   INTEGER NOT NULL,
                operation    TEXT    NOT NULL,
                params_json  TEXT,
                outcome      TEXT    NOT NULL CHECK(outcome IN ('success','failure','skipped')),
                result_json  TEXT,
                error        TEXT,
                api_calls    INTEGER NOT NULL DEFAULT 0,
                duration_ms  INTEGER NOT NULL DEFAULT 0
            )
        """)

        # What the agent learned from this run (extracted knowledge)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS execution_learnings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       TEXT    NOT NULL REFERENCES executions(run_id),
                learning_type TEXT   NOT NULL,
                subject      TEXT    NOT NULL,
                observation  TEXT    NOT NULL,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # --- Capability Memory ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capabilities (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    NOT NULL UNIQUE,
                description      TEXT    NOT NULL,
                operation_type   TEXT    NOT NULL,
                implementation   TEXT    NOT NULL,
                is_synthesized   INTEGER NOT NULL DEFAULT 0,
                success_count    INTEGER NOT NULL DEFAULT 0,
                failure_count    INTEGER NOT NULL DEFAULT 0,
                avg_duration_ms  REAL    NOT NULL DEFAULT 0.0,
                constraints_json TEXT,
                synthesized_at   TEXT,
                last_used_at     TEXT
            )
        """)

        # Constraints discovered at runtime (rate limits, field validation, etc.)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovered_constraints (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                capability  TEXT    NOT NULL,
                constraint_type TEXT NOT NULL,
                description TEXT    NOT NULL,
                discovered_at TEXT  NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Intent patterns → best capability mapping (for tool selection improvement)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intent_patterns (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern         TEXT    NOT NULL,
                capability_name TEXT    NOT NULL REFERENCES capabilities(name),
                success_rate    REAL    NOT NULL DEFAULT 1.0,
                sample_count    INTEGER NOT NULL DEFAULT 1,
                updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Learning metrics per task type for the measurable improvement signal
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_metrics (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                intent_hash    TEXT    NOT NULL,
                task_label     TEXT    NOT NULL,
                run_number     INTEGER NOT NULL,
                api_calls      INTEGER NOT NULL,
                duration_ms    INTEGER NOT NULL,
                outcome        TEXT    NOT NULL,
                optimizations  TEXT,
                recorded_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

    conn.close()
