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

    t = Table(box=box.SIMPLE)
    t.add_column("Metric")
    t.add_column("Run 1", justify="right")
    t.add_column("Latest", justify="right")
    t.add_column("Delta", justify="right")

    api_delta = report["first_run"]["api_calls"] - report["latest_run"]["api_calls"]
    time_delta = report["first_run"]["duration_ms"] - report["latest_run"]["duration_ms"]

    t.add_row(
        "API calls",
        str(report["first_run"]["api_calls"]),
        str(report["latest_run"]["api_calls"]),
        f"[green]-{api_delta}[/green]" if api_delta > 0 else f"[red]+{-api_delta}[/red]",
    )
    t.add_row(
        "Duration (ms)",
        str(report["first_run"]["duration_ms"]),
        str(report["latest_run"]["duration_ms"]),
        f"[green]-{time_delta}ms[/green]" if time_delta > 0 else f"[red]+{-time_delta}ms[/red]",
    )
    console.print(t)

    if report["api_calls_saved"] > 0:
        console.print(
            f"\n[bold green]✓ {report['api_calls_saved']} fewer API calls "
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
