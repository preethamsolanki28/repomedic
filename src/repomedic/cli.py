import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

# Load local environment credentials if present (keeps credentials out of git)
load_dotenv()

from repomedic.workspace import (
    WorkspaceManager,
    ConflictError,
    SecurityTraversalError,
)

app = typer.Typer(
    name="repomedic",
    help="RepoMedic: Local-first AI repository repair tool",
    add_completion=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show RepoMedic version.",
        is_eager=True,
    ),
) -> None:
    """RepoMedic: Local-first AI repository repair tool."""
    if version:
        console.print("[bold cyan]RepoMedic[/bold cyan] v0.1.0")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@app.command()
def fix(
    path: Path = typer.Argument(
        Path("."),
        help="Path to the target repository or project directory",
    ),
    error: Optional[str] = typer.Option(
        None,
        "--error",
        "-e",
        help="Optional error message or build log to diagnose",
    ),
    no_prompt_error: bool = typer.Option(
        False,
        "--no-prompt-error",
        help="Do not prompt for an error message",
    ),
    accept: bool = typer.Option(
        False,
        "--accept",
        "-y",
        help="Accept and apply the proposed changes without prompting",
    ),
    reject: bool = typer.Option(
        False,
        "--reject",
        "-n",
        help="Reject and discard the proposed changes without prompting",
    ),
) -> None:
    """Diagnose and repair project errors in an isolated safe workspace."""
    resolved_path = path.resolve()
    if not resolved_path.exists():
        console.print(f"[bold red]Error:[/bold red] Target path does not exist: {path}")
        raise typer.Exit(code=1)
    if not resolved_path.is_dir():
        console.print(f"[bold red]Error:[/bold red] Target path is not a directory: {path}")
        raise typer.Exit(code=1)

    # 1. Optional error message prompt
    error_text = error
    if error_text is None and not no_prompt_error:
        try:
            prompted = typer.prompt(
                "Paste error message (or press Enter to investigate automatically)",
                default="",
                show_default=False,
            )
            if prompted.strip():
                error_text = prompted.strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Aborted by user.[/dim]")
            raise typer.Exit(code=1)

    if error_text:
        console.print(f"[dim]Diagnostic hint received ({len(error_text)} chars)[/dim]")

    # 2. Safe workspace creation
    wm = WorkspaceManager()
    console.print(f"[bold cyan]RepoMedic[/bold cyan] — Preparing safe workspace for [bold]{resolved_path.name}[/bold]...")

    try:
        ws_dir, baseline = wm.create_workspace(resolved_path)
    except Exception as exc:
        console.print(f"[bold red]Error creating workspace:[/bold red] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[green]✓[/green] Isolated workspace created at: [dim]{ws_dir}[/dim]")

    # 3. Agent diagnosis, repair, and verification step
    console.print("[bold cyan]RepoMedic[/bold cyan] — Initiating LangGraph Diagnose → Fix → Docker Verify workflow...")

    service = None
    if os.getenv("ARMORIQ_API_KEY") and os.getenv("ARMORIQ_USER_EMAIL"):
        try:
            from repomedic.security.armoriq_service import ArmorIQService
            service = ArmorIQService(config_path="armoriq.yaml")
        except Exception as exc:
            console.print(f"[dim]ArmorIQ disabled or unavailable: {exc}[/dim]")

    nm_path = None
    if (resolved_path / "node_modules").exists():
        nm_path = str(resolved_path / "node_modules")

    from repomedic.workflow import build_repair_graph, RepairState

    graph = build_repair_graph(armoriq_service=service)
    initial_state: RepairState = {
        "workspace_dir": str(ws_dir),
        "source_node_modules": nm_path,
        "project_name": resolved_path.name,
        "pasted_error": error_text,
        "diagnosis": None,
        "repair_plan": [],
        "approved_files": [],
        "check_results": [],
        "retry_count": 0,
        "armoriq_events": [],
        "security_denial_evidence": None,
        "status": "diagnosing",
    }

    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        console.print(f"[bold red]Workflow error:[/bold red] {exc}")
        wm.discard_workspace(ws_dir)
        raise typer.Exit(code=1)

    # 4. Terminal Repair Receipt
    receipt_lines = []
    if final_state.get("diagnosis"):
        receipt_lines.append(f"[bold cyan]Diagnosis:[/bold cyan]\n{final_state['diagnosis']}\n")

    if final_state.get("repair_plan"):
        plan_str = "\n".join(f"  • {step}" for step in final_state["repair_plan"])
        receipt_lines.append(f"[bold cyan]Repair Plan:[/bold cyan]\n{plan_str}\n")

    if final_state.get("check_results"):
        receipt_lines.append("[bold cyan]Verification Checks (Docker network=none):[/bold cyan]")
        for cr in final_state["check_results"]:
            icon = "[green]✓ PASSED[/green]" if cr.passed else "[red]✗ FAILED[/red]"
            receipt_lines.append(f"  • {cr.name}: {icon} (exit code {cr.exit_code})")
        receipt_lines.append("")

    if final_state.get("security_denial_evidence"):
        receipt_lines.append(f"[bold yellow]ArmorIQ Enforcement Evidence:[/bold yellow]\n  {final_state['security_denial_evidence']}\n")

    status_color = "green" if final_state.get("status") == "complete" else "yellow"
    receipt_lines.append(f"[bold]Workflow Outcome:[/bold] [{status_color}]{final_state.get('status', '').upper()}[/{status_color}] (Retries: {final_state.get('retry_count', 0)})")

    console.print(Panel("\n".join(receipt_lines), title="[bold]RepoMedic Repair Receipt[/bold]", border_style=status_color))

    diff = wm.compute_diff(resolved_path, ws_dir)

    # 5. Diff preview
    if diff:
        syntax = Syntax(diff, "diff", theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title="Proposed Changes (Unified Diff)", border_style="cyan"))
    else:
        console.print("[dim]No modifications were made to the workspace.[/dim]")

    # 5. Accept / Reject workflow
    if reject:
        wm.discard_workspace(ws_dir)
        console.print("[yellow]Changes rejected. Workspace discarded; original files left untouched.[/yellow]")
        return

    if accept:
        try:
            applied = wm.apply_changes(resolved_path, ws_dir, baseline)
            if applied:
                console.print(f"[bold green]✓[/bold green] Applied patch to {len(applied)} file(s): {', '.join(applied)}")
            else:
                console.print("[green]✓[/green] No changes needed. Workspace cleaned up.")
        except ConflictError as exc:
            console.print(f"[bold red]Conflict error:[/bold red] {exc}")
            wm.discard_workspace(ws_dir)
            raise typer.Exit(code=1)
        except SecurityTraversalError as exc:
            console.print(f"[bold red]Security error:[/bold red] {exc}")
            wm.discard_workspace(ws_dir)
            raise typer.Exit(code=1)
        return

    # Interactive decision
    if not diff:
        wm.discard_workspace(ws_dir)
        console.print("[dim]Workspace discarded; original files left untouched.[/dim]")
        return

    try:
        choice = typer.prompt("Accept and apply changes to original repository? [a/r]", default="r")
    except (KeyboardInterrupt, EOFError):
        choice = "r"

    if choice.strip().lower().startswith("a"):
        try:
            applied = wm.apply_changes(resolved_path, ws_dir, baseline)
            console.print(f"[bold green]✓[/bold green] Applied patch to {len(applied)} file(s): {', '.join(applied)}")
        except ConflictError as exc:
            console.print(f"[bold red]Conflict error:[/bold red] {exc}")
            wm.discard_workspace(ws_dir)
            raise typer.Exit(code=1)
        except SecurityTraversalError as exc:
            console.print(f"[bold red]Security error:[/bold red] {exc}")
            wm.discard_workspace(ws_dir)
            raise typer.Exit(code=1)
    else:
        wm.discard_workspace(ws_dir)
        console.print("[yellow]Changes rejected. Workspace discarded; original files left untouched.[/yellow]")


if __name__ == "__main__":
    app()
