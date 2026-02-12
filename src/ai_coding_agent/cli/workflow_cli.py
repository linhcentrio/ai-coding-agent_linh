"""
Workflow CLI Commands
======================
CLI commands for managing and executing workflows.
"""

import asyncio
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..orchestrator import WorkflowEngine, WorkflowConfig, ExecutionMode
from ..providers.gemini import GeminiProvider
from ..providers.claude import ClaudeProvider
from ..providers.codex import CodexProvider


console = Console()


def get_providers():
    """Initialize all available providers."""
    providers = {}
    
    try:
        providers["gemini"] = GeminiProvider()
    except Exception:
        pass
    
    try:
        providers["claude"] = ClaudeProvider()
    except Exception:
        pass
    
    try:
        providers["codex"] = CodexProvider()
    except Exception:
        pass
    
    return providers


@click.group()
def workflow():
    """Workflow management commands."""
    pass


@workflow.command("list")
@click.option(
    "-d", "--dir",
    type=click.Path(exists=True),
    default=None,
    help="Workflow directory",
)
def list_workflows(dir: Optional[str]):
    """List available workflows."""
    providers = get_providers()
    engine = WorkflowEngine(providers)
    
    # Load workflows
    workflow_dir = Path(dir) if dir else Path(__file__).parent.parent.parent.parent.parent / "config" / "workflows"
    
    if workflow_dir.exists():
        engine.load_workflows_dir(workflow_dir)
    
    if not engine.workflows:
        console.print("[yellow]No workflows found[/yellow]")
        return
    
    table = Table(title="Available Workflows")
    table.add_column("Name", style="cyan")
    table.add_column("Mode", style="green")
    table.add_column("Steps", style="yellow")
    table.add_column("Description")
    
    for name, wf in engine.workflows.items():
        table.add_row(
            name,
            wf.mode.value,
            str(len(wf.steps)),
            wf.description[:50] + "..." if len(wf.description) > 50 else wf.description
        )
    
    console.print(table)


@workflow.command("run")
@click.argument("name")
@click.argument("task")
@click.option(
    "-d", "--dir",
    type=click.Path(exists=True),
    default=None,
    help="Workflow directory",
)
def run_workflow(name: str, task: str, dir: Optional[str]):
    """Run a workflow by name."""
    providers = get_providers()
    
    if not providers:
        console.print("[red]No providers available. Set API keys first.[/red]")
        return
    
    engine = WorkflowEngine(providers)
    
    # Load workflows
    workflow_dir = Path(dir) if dir else Path(__file__).parent.parent.parent.parent.parent / "config" / "workflows"
    
    if workflow_dir.exists():
        engine.load_workflows_dir(workflow_dir)
    
    wf = engine.get_workflow(name)
    if not wf:
        console.print(f"[red]Workflow not found: {name}[/red]")
        return
    
    console.print(Panel(
        f"[bold]{wf.name}[/bold]\n"
        f"Mode: {wf.mode.value}\n"
        f"Steps: {len(wf.steps)}",
        title="🔄 Running Workflow"
    ))
    
    async def execute():
        result = await engine.execute(name, task)
        return result
    
    result = asyncio.run(execute())
    
    if result.success:
        console.print("\n[green]✅ Workflow completed successfully[/green]")
    else:
        console.print("\n[red]❌ Workflow failed[/red]")
    
    console.print(f"\nIterations: {result.total_iterations}")
    console.print(f"\n[bold]Final Output:[/bold]")
    console.print(result.final_output[:2000] if len(result.final_output) > 2000 else result.final_output)


@workflow.command("show")
@click.argument("name")
@click.option(
    "-d", "--dir",
    type=click.Path(exists=True),
    default=None,
    help="Workflow directory",
)
def show_workflow(name: str, dir: Optional[str]):
    """Show workflow details."""
    providers = get_providers()
    engine = WorkflowEngine(providers)
    
    workflow_dir = Path(dir) if dir else Path(__file__).parent.parent.parent.parent.parent / "config" / "workflows"
    
    if workflow_dir.exists():
        engine.load_workflows_dir(workflow_dir)
    
    wf = engine.get_workflow(name)
    if not wf:
        console.print(f"[red]Workflow not found: {name}[/red]")
        return
    
    console.print(Panel(
        f"[bold]Name:[/bold] {wf.name}\n"
        f"[bold]Description:[/bold] {wf.description}\n"
        f"[bold]Mode:[/bold] {wf.mode.value}\n"
        f"[bold]Max Rounds:[/bold] {wf.max_rounds}\n"
        f"[bold]Merge Strategy:[/bold] {wf.merge_strategy}",
        title="📋 Workflow Details"
    ))
    
    console.print("\n[bold]Steps:[/bold]")
    for i, step in enumerate(wf.steps, 1):
        console.print(f"  {i}. [cyan]{step.agent}[/cyan] ({step.role})")
    
    if wf.stop_conditions:
        console.print("\n[bold]Stop Conditions:[/bold]")
        for cond in wf.stop_conditions:
            console.print(f"  - {cond.type}: {cond.value}")
