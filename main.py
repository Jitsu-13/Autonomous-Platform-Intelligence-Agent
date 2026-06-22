"""
Autonomous Platform Intelligence Agent — Linear
Usage: python main.py run "your natural language instruction"
"""

import os
import json
import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

load_dotenv()

console = Console()


@click.group()
def cli():
    """Autonomous Platform Intelligence Agent for Linear."""
    pass


@cli.command("run")
@click.argument("instruction")
@click.option("--verbose", "-v", is_flag=True, help="Show step-by-step execution")
@click.option("--json-output", "-j", is_flag=True, help="Output raw JSON report")
def run_cmd(instruction, verbose, json_output):
    """Run a natural language instruction against Linear."""
    from agent.core.orchestrator import run

    if not json_output:
        console.print(Panel(
            f"[bold cyan]{instruction}[/bold cyan]",
            title="[bold]Autonomous Linear Agent[/bold]",
            border_style="cyan",
        ))

    report = run(instruction, verbose=verbose)

    if json_output:
        click.echo(json.dumps(report.model_dump(), indent=2, default=str))
        return

    _render_report(report)


@cli.command("memory")
def show_memory():
    """Show current memory state (execution + capability layers)."""
    from agent.memory.manager import boot, get_memory_stats
    from agent.memory.capability_store import get_all_capabilities

    boot()
    stats = get_memory_stats()
    caps = get_all_capabilities()

    console.print(Panel("[bold]Memory State[/bold]", border_style="green"))

    stats_table = Table(box=box.SIMPLE)
    stats_table.add_column("Layer", style="bold")
    stats_table.add_column("Records", justify="right")
    for k, v in stats.items():
        stats_table.add_row(k.replace("_", " ").title(), str(v))
    console.print(stats_table)

    if caps:
        cap_table = Table(title="Capabilities", box=box.SIMPLE)
        cap_table.add_column("Name", style="cyan")
        cap_table.add_column("Type")
        cap_table.add_column("Synth?", justify="center")
        cap_table.add_column("OK", justify="right", style="green")
        cap_table.add_column("Fail", justify="right", style="red")
        cap_table.add_column("Avg ms", justify="right")
        for c in caps:
            cap_table.add_row(
                c["name"],
                c["operation_type"],
                "★" if c["is_synthesized"] else "",
                str(c["success_count"]),
                str(c["failure_count"]),
                str(int(c["avg_duration_ms"] or 0)),
            )
        console.print(cap_table)


@cli.command("improvement")
@click.argument("instruction")
def show_improvement(instruction):
    """Show learning improvement metrics for a type of instruction."""
    from agent.memory.manager import boot
    from agent.learning.feedback import get_improvement_report

    boot()
    report = get_improvement_report(instruction)

    if "message" in report:
        console.print(f"[yellow]{report['message']}[/yellow]")
        return

    console.print(Panel("[bold]Learning Improvement Report[/bold]", border_style="yellow"))
    console.print(f"Instruction type: [cyan]{report['instruction_type']}[/cyan]")
    console.print(f"Total runs: [bold]{report['total_runs']}[/bold]")
    console.print()

    # Per-run progression table
    prog = Table(title="Run History", box=box.SIMPLE)
    prog.add_column("Run", justify="right", width=4)
    prog.add_column("Outcome", width=10)
    prog.add_column("API Calls", justify="right", width=9)
    prog.add_column("Duration (ms)", justify="right", width=13)
    outcome_colors = {"success": "green", "partial": "yellow", "failure": "red"}
    for row in report["all_runs"]:
        oc = row["outcome"]
        col = outcome_colors.get(oc, "white")
        prog.add_row(
            str(row["run_number"]),
            f"[{col}]{oc}[/{col}]",
            str(row["api_calls"]),
            str(row["duration_ms"]),
        )
    console.print(prog)

    first_oc = report["first_run"]["outcome"]
    latest_oc = report["latest_run"]["outcome"]
    outcome_improved = first_oc != latest_oc and latest_oc == "success"

    # When run 1 was a partial failure, comparing API calls vs run 1 is misleading
    # (partial runs make fewer calls because they stop early, not because they're efficient).
    # Use the first SUCCESSFUL run as the baseline for API/timing comparison instead.
    baseline = next(
        (r for r in report["all_runs"] if r["outcome"] == "success"),
        report["latest_run"],
    )
    baseline_label = f"Run {baseline['run_number']} (1st success)" if baseline != report["first_run"] else "Run 1"

    api_delta = baseline["api_calls"] - report["latest_run"]["api_calls"]
    time_delta = baseline["duration_ms"] - report["latest_run"]["duration_ms"]

    partial_count = sum(1 for r in report["all_runs"] if r["outcome"] != "success")
    success_count = sum(1 for r in report["all_runs"] if r["outcome"] == "success")

    t = Table(title="Summary", box=box.SIMPLE)
    t.add_column("Metric")
    t.add_column("Run 1", justify="right")
    t.add_column(baseline_label, justify="right")
    t.add_column("Latest", justify="right")

    t.add_row(
        "Outcome",
        f"[{outcome_colors.get(first_oc,'white')}]{first_oc}[/{outcome_colors.get(first_oc,'white')}]",
        f"[{outcome_colors.get(baseline['outcome'],'white')}]{baseline['outcome']}[/{outcome_colors.get(baseline['outcome'],'white')}]",
        f"[{outcome_colors.get(latest_oc,'white')}]{latest_oc}[/{outcome_colors.get(latest_oc,'white')}]",
    )
    t.add_row(
        "API calls",
        str(report["first_run"]["api_calls"]),
        str(baseline["api_calls"]),
        str(report["latest_run"]["api_calls"]),
    )
    t.add_row(
        "Duration (ms)",
        str(report["first_run"]["duration_ms"]),
        str(baseline["duration_ms"]),
        str(report["latest_run"]["duration_ms"]),
    )
    console.print(t)

    if outcome_improved:
        console.print(
            f"\n[bold green]Outcome improved: {partial_count} partial run(s) then "
            f"{success_count} consecutive success(es)[/bold green]"
        )
        if first_oc != "success":
            console.print(
                f"[dim]Run 1 was '{first_oc}' (stopped early = fewer API calls). "
                f"API/timing comparison uses {baseline_label} as the fair baseline.[/dim]"
            )
    elif api_delta > 0:
        console.print(
            f"\n[bold green]{api_delta} fewer API calls "
            f"({report['improvement_pct']}% improvement)[/bold green]"
        )


def _render_report(report) -> None:
    outcome_color = {"success": "green", "partial": "yellow", "failure": "red"}[report.overall_outcome]

    console.print(Panel(
        f"[bold {outcome_color}]{report.overall_outcome.upper()}[/bold {outcome_color}]  "
        f"[dim]{report.steps_succeeded}/{report.steps_total} steps[/dim]  "
        f"[dim]{report.api_calls_total} API calls  {report.duration_ms}ms[/dim]",
        title=f"[dim]run {report.run_id[:8]}[/dim]",
        border_style=outcome_color,
    ))

    t = Table(box=box.SIMPLE_HEAD, show_header=True)
    t.add_column("#", width=3)
    t.add_column("Step", min_width=30)
    t.add_column("Status", width=10)
    t.add_column("API", justify="right", width=5)
    t.add_column("ms", justify="right", width=7)
    t.add_column("Note", min_width=30)

    for step in report.step_results:
        color = {"success": "green", "failure": "red", "skipped": "dim"}[step.outcome]
        note = ""
        if step.outcome == "failure":
            note = (step.error or "")[:60]
        elif step.outcome == "success" and step.data:
            keys = list(step.data.keys())[:3]
            note = ", ".join(keys)

        t.add_row(
            str(step.step_index),
            step.description[:45],
            f"[{color}]{step.outcome}[/{color}]",
            str(step.api_calls),
            str(step.duration_ms),
            note,
        )
    console.print(t)

    if report.memory_applied:
        console.print("[bold cyan]Memory applied:[/bold cyan]")
        for m in report.memory_applied:
            console.print(f"  • {m}")

    if report.synthesized_capabilities:
        console.print(f"[bold magenta]Synthesized capabilities:[/bold magenta] {', '.join(report.synthesized_capabilities)}")

    if report.learnings_extracted:
        console.print("[bold yellow]Learnings recorded:[/bold yellow]")
        for ln in report.learnings_extracted:
            console.print(f"  • {ln}")


if __name__ == "__main__":
    cli()
