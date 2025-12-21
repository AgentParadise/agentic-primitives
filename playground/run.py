#!/usr/bin/env python3
"""Agentic Playground CLI - Run agents with live OTel events.

Usage:
    # Run a simple task
    python run.py "Create a hello world script"

    # Run with live OTel events
    python run.py "Create a hello world script" --live

    # Use a specific scenario
    python run.py "Review this code" --scenario security-audit

    # Use local provider (no Docker)
    python run.py "List files" --local

    # Use otel-tui for visualization
    python run.py "Create a script" --tui
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from src.config import list_scenarios, load_scenario
from src.display import EventDisplay, create_output_callback
from src.executor import AgentExecutor
from src.receiver import OTLPReceiver, create_receiver_callback

app = typer.Typer(
    name="playground",
    help="Interactive playground for testing agentic-primitives with live OTel events.",
)
console = Console()


@app.command()
def run(
    task: str = typer.Argument(..., help="The task to give the agent"),
    scenario: str = typer.Option(
        "default",
        "--scenario", "-s",
        help="Scenario name from scenarios/ directory",
    ),
    live: bool = typer.Option(
        False,
        "--live", "-l",
        help="Show inline OTel events in terminal",
    ),
    tui: bool = typer.Option(
        False,
        "--tui", "-t",
        help="Use otel-tui for visualization (requires Docker Compose up)",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="Use local provider instead of Docker",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output",
    ),
    otel_port: int = typer.Option(
        4317,
        "--otel-port",
        help="OTLP receiver port (for --live mode)",
    ),
) -> None:
    """Run an agent with the given task."""
    asyncio.run(_run_async(
        task=task,
        scenario_name=scenario,
        live=live,
        tui=tui,
        local=local,
        verbose=verbose,
        otel_port=otel_port,
    ))


async def _run_async(
    task: str,
    scenario_name: str,
    live: bool,
    tui: bool,
    local: bool,
    verbose: bool,
    otel_port: int,
) -> None:
    """Async implementation of run command."""
    # Load scenario
    try:
        config = load_scenario(scenario_name)
        if verbose:
            console.print(f"[green]✓[/green] Loaded scenario: {config.name}")
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Scenario '{scenario_name}' not found")
        console.print(f"Available scenarios: {', '.join(list_scenarios())}")
        raise typer.Exit(1) from None

    # Override provider if --local
    if local:
        config.isolation.provider = "local"

    # Setup display
    display = EventDisplay(console)

    # Determine OTel endpoint
    if live:
        # Use inline receiver
        otel_endpoint = f"http://localhost:{otel_port}"
    elif tui:
        # Use otel-tui (assumes Docker Compose is running)
        otel_endpoint = "http://localhost:4317"
        console.print("[yellow]Note:[/yellow] Ensure otel-tui is running: docker compose up -d")
    else:
        # Use Docker internal endpoint
        if config.isolation.provider == "docker":
            otel_endpoint = "http://host.docker.internal:4317"
        else:
            otel_endpoint = "http://localhost:4317"

    # Create executor
    executor = AgentExecutor(
        config=config,
        otel_endpoint=otel_endpoint,
        on_output=create_output_callback(display, live=live),
    )

    console.print()
    console.print("[bold cyan]🚀 Agentic Playground[/bold cyan]")
    console.print(f"[dim]Session: {executor.session_id}[/dim]")
    console.print()

    if live:
        # Start OTLP receiver and live display
        receiver_callback = create_receiver_callback(display.add_event)

        with OTLPReceiver(receiver_callback, port=otel_port):
            if verbose:
                console.print(f"[green]✓[/green] OTLP receiver started on port {otel_port}")

            display.start_live()
            try:
                result = await executor.run(task, verbose=verbose)
            finally:
                display.stop_live()
    else:
        # Run without live display
        result = await executor.run(task, verbose=verbose)

    # Show results
    display.print_result(
        success=result.success,
        duration=result.duration_seconds,
        exit_code=result.exit_code,
        stdout=result.stdout if verbose or not result.success else None,
    )

    if live:
        display.print_summary()

    if result.created_files:
        console.print()
        console.print("[bold]Created files:[/bold]")
        for f in result.created_files:
            console.print(f"  • {f}")

    # Exit with agent's exit code
    raise typer.Exit(result.exit_code)


@app.command()
def scenarios() -> None:
    """List available scenarios."""
    available = list_scenarios()

    if not available:
        console.print("[yellow]No scenarios found in scenarios/ directory[/yellow]")
        return

    console.print("[bold]Available scenarios:[/bold]")
    for name in available:
        try:
            config = load_scenario(name)
            console.print(f"  • [cyan]{name}[/cyan]: {config.description or 'No description'}")
        except Exception:
            console.print(f"  • [cyan]{name}[/cyan]: [red](error loading)[/red]")


@app.command()
def info() -> None:
    """Show playground information."""
    console.print("[bold cyan]Agentic Playground[/bold cyan]")
    console.print()
    console.print("[bold]Usage:[/bold]")
    console.print("  python run.py \"Your task here\"")
    console.print()
    console.print("[bold]Options:[/bold]")
    console.print("  --live       Show inline OTel events")
    console.print("  --tui        Use otel-tui visualization")
    console.print("  --local      Use local provider (no Docker)")
    console.print("  --scenario   Use a specific scenario")
    console.print("  --verbose    Enable verbose output")
    console.print()
    console.print("[bold]Scenarios:[/bold]")
    for name in list_scenarios():
        console.print(f"  • {name}")


if __name__ == "__main__":
    app()
