"""Rich Terminal Display for OTel Events.

This module provides a live terminal display for OTel events
using the Rich library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class EventType(Enum):
    """Types of OTel events we display."""

    TRACE = "trace"
    METRIC = "metric"
    LOG = "log"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    SECURITY = "security"


@dataclass
class DisplayEvent:
    """Event to display in the terminal."""

    timestamp: datetime
    event_type: EventType
    name: str
    value: str
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def type_color(self) -> str:
        """Get color for event type."""
        colors = {
            EventType.TRACE: "blue",
            EventType.METRIC: "green",
            EventType.LOG: "yellow",
            EventType.TOOL_START: "cyan",
            EventType.TOOL_END: "cyan",
            EventType.SECURITY: "red",
        }
        return colors.get(self.event_type, "white")


class EventDisplay:
    """Rich terminal display for OTel events.

    Provides a live-updating table of events with color coding
    and a summary panel.
    """

    def __init__(
        self,
        console: Console | None = None,
        max_events: int = 50,
    ):
        """Initialize display.

        Args:
            console: Rich console (creates new if None)
            max_events: Maximum events to keep in display
        """
        self.console = console or Console()
        self.max_events = max_events
        self.events: list[DisplayEvent] = []
        self._live: Live | None = None

        # Summary stats
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.tool_calls = 0
        self.security_blocks = 0

    def add_event(self, event: DisplayEvent) -> None:
        """Add an event to the display.

        Args:
            event: Event to add
        """
        self.events.append(event)

        # Update stats
        if event.event_type == EventType.METRIC:
            if "tokens_in" in event.name.lower() and event.value.isdigit():
                self.total_tokens_in += int(event.value)
            elif "tokens_out" in event.name.lower() and event.value.isdigit():
                self.total_tokens_out += int(event.value)
        elif event.event_type == EventType.TOOL_START:
            self.tool_calls += 1
        elif event.event_type == EventType.SECURITY and "blocked" in event.value.lower():
            self.security_blocks += 1

        # Trim to max events
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]

        # Update live display if running
        if self._live:
            self._live.update(self._build_layout())

    def _build_events_table(self) -> Table:
        """Build the events table."""
        table = Table(
            title="Live Events",
            show_header=True,
            header_style="bold magenta",
            expand=True,
        )

        table.add_column("Time", style="dim", width=10)
        table.add_column("Type", width=12)
        table.add_column("Name", width=20)
        table.add_column("Value", ratio=1)

        for event in self.events[-20:]:  # Show last 20
            time_str = event.timestamp.strftime("%H:%M:%S")
            type_text = Text(event.event_type.value.upper())
            type_text.stylize(event.type_color)

            # Truncate value if too long
            value = event.value[:80] + "..." if len(event.value) > 80 else event.value

            table.add_row(time_str, type_text, event.name, value)

        return table

    def _build_summary_panel(self) -> Panel:
        """Build the summary panel."""
        summary = Table.grid(padding=1)
        summary.add_column(justify="right", style="cyan")
        summary.add_column(justify="left")

        summary.add_row("Tokens In:", f"{self.total_tokens_in:,}")
        summary.add_row("Tokens Out:", f"{self.total_tokens_out:,}")
        summary.add_row("Tool Calls:", str(self.tool_calls))
        summary.add_row("Security Blocks:", str(self.security_blocks))
        summary.add_row("Events:", str(len(self.events)))

        return Panel(summary, title="Summary", border_style="green")

    def _build_layout(self) -> Table:
        """Build the full layout."""
        layout = Table.grid(expand=True)
        layout.add_column(ratio=3)
        layout.add_column(ratio=1)

        layout.add_row(
            self._build_events_table(),
            self._build_summary_panel(),
        )

        return layout

    def start_live(self) -> None:
        """Start live display mode."""
        self._live = Live(
            self._build_layout(),
            console=self.console,
            refresh_per_second=4,
        )
        self._live.start()

    def stop_live(self) -> None:
        """Stop live display mode."""
        if self._live:
            self._live.stop()
            self._live = None

    def print_event(self, event: DisplayEvent) -> None:
        """Print a single event (non-live mode).

        Args:
            event: Event to print
        """
        time_str = event.timestamp.strftime("%H:%M:%S")
        type_text = Text(f"[{event.event_type.value.upper():^10}]")
        type_text.stylize(event.type_color)

        self.console.print(
            f"[dim]{time_str}[/dim] ",
            type_text,
            f" {event.name}: {event.value}",
        )

    def print_summary(self) -> None:
        """Print final summary."""
        self.console.print()
        self.console.print(Panel(
            f"[cyan]Tokens:[/cyan] {self.total_tokens_in:,} in / {self.total_tokens_out:,} out\n"
            f"[cyan]Tools:[/cyan] {self.tool_calls} calls\n"
            f"[cyan]Security:[/cyan] {self.security_blocks} blocks\n"
            f"[cyan]Events:[/cyan] {len(self.events)} total",
            title="Execution Summary",
            border_style="green",
        ))

    def print_result(
        self,
        success: bool,
        duration: float,
        exit_code: int,
        stdout: str | None = None,
    ) -> None:
        """Print execution result.

        Args:
            success: Whether execution succeeded
            duration: Duration in seconds
            exit_code: Exit code
            stdout: Optional stdout to display
        """
        status = "[green]SUCCESS[/green]" if success else "[red]FAILED[/red]"

        self.console.print()
        self.console.print(Panel(
            f"Status: {status}\n"
            f"Exit Code: {exit_code}\n"
            f"Duration: {duration:.1f}s",
            title="Result",
            border_style="green" if success else "red",
        ))

        if stdout:
            # Truncate if too long
            display_stdout = stdout[:2000]
            if len(stdout) > 2000:
                display_stdout += "\n... [truncated]"

            self.console.print()
            self.console.print(Panel(
                display_stdout,
                title="Output",
                border_style="blue",
            ))


def create_output_callback(display: EventDisplay, live: bool = False) -> callable:
    """Create an output callback for the executor.

    Args:
        display: EventDisplay instance
        live: Whether to use live mode

    Returns:
        Callback function
    """
    def callback(message: str) -> None:
        if live:
            # In live mode, add as log event
            event = DisplayEvent(
                timestamp=datetime.now(),
                event_type=EventType.LOG,
                name="executor",
                value=message,
            )
            display.add_event(event)
        else:
            # In normal mode, just print
            display.console.print(message)

    return callback
