import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

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

    # 3. Agent diagnosis and repair step
    # Note: AI agent workflow (Diagnoser -> Fixer -> Docker verify) will be wired in M3/M4.
    # The workspace currently holds the clean isolated copy.

    diff = wm.compute_diff(resolved_path, ws_dir)

    # 4. Diff preview
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
