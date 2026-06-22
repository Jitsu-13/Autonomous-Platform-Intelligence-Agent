"""Pydantic models for plans, steps, and execution reports."""

from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel, Field
import time


class PlannedStep(BaseModel):
    step_index: int
    capability: str
    description: str
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)
    is_optional: bool = False


class ExecutionPlan(BaseModel):
    instruction: str
    intent_summary: str
    steps: list[PlannedStep]
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    memory_used: bool = False
    memory_insights: list[str] = Field(default_factory=list)


class StepResult(BaseModel):
    step_index: int
    capability: str
    description: str
    outcome: str                        # success | failure | skipped
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    api_calls: int = 0
    duration_ms: int = 0


class ExecutionReport(BaseModel):
    run_id: str
    instruction: str
    overall_outcome: str                # success | partial | failure
    steps_total: int
    steps_succeeded: int
    steps_failed: int
    steps_skipped: int
    step_results: list[StepResult]
    api_calls_total: int
    duration_ms: int
    tokens_used: int = 0
    memory_applied: list[str] = Field(default_factory=list)
    learnings_extracted: list[str] = Field(default_factory=list)
    synthesized_capabilities: list[str] = Field(default_factory=list)
    error_summary: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.overall_outcome == "success"

    def summary_lines(self) -> list[str]:
        lines = [
            f"Run: {self.run_id}",
            f"Outcome: {self.overall_outcome.upper()}",
            f"Steps: {self.steps_succeeded}/{self.steps_total} succeeded"
            + (f", {self.steps_failed} failed" if self.steps_failed else "")
            + (f", {self.steps_skipped} skipped" if self.steps_skipped else ""),
            f"API calls: {self.api_calls_total}  |  Time: {self.duration_ms}ms",
        ]
        if self.memory_applied:
            lines.append(f"Memory applied: {'; '.join(self.memory_applied)}")
        if self.synthesized_capabilities:
            lines.append(f"Synthesized: {', '.join(self.synthesized_capabilities)}")
        if self.error_summary:
            lines.append(f"Errors: {self.error_summary}")
        return lines
