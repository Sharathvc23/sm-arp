"""Output formatting for the ARP CLI.

Plain text with light ANSI styling via typer.style. No rich dependency.
Width is fixed at 78 columns so output looks consistent in narrow shells.
"""

from __future__ import annotations

import typer


WIDTH = 78


def banner(title: str) -> None:
    """Top-of-output title bar — used by `arp demo`."""
    bar = "═" * WIDTH
    typer.secho(bar, fg=typer.colors.BRIGHT_BLUE)
    typer.secho(f"  {title}", bold=True)
    typer.secho(bar, fg=typer.colors.BRIGHT_BLUE)


def step_header(step_num: int, total: int, title: str) -> None:
    """Step-N-of-M header for demo flows."""
    label = f" Step {step_num}/{total}: {title} "
    pad = "─" * (WIDTH - len(label) - 1)
    typer.echo()
    typer.secho(f"┌─{label}{pad}", fg=typer.colors.CYAN, bold=True)


def section(title: str) -> None:
    """Stand-alone section heading — used by single-command output."""
    label = f" {title} "
    pad = "─" * (WIDTH - len(label) - 1)
    typer.echo()
    typer.secho(f"┌─{label}{pad}", fg=typer.colors.CYAN, bold=True)


def kv(key: str, value: str, *, indent: int = 2, key_width: int = 14) -> None:
    """Aligned key-value pair."""
    pad = " " * indent
    typer.echo(f"{pad}{key:<{key_width}} {value}")


def ok(message: str) -> None:
    """Green checkmark line."""
    typer.echo(
        "  "
        + typer.style("✓ ", fg=typer.colors.GREEN, bold=True)
        + typer.style(message, fg=typer.colors.GREEN)
    )


def fail(message: str) -> None:
    """Red cross line — used for expected-fail vectors too, so not always an error."""
    typer.echo(
        "  "
        + typer.style("✗ ", fg=typer.colors.RED, bold=True)
        + typer.style(message, fg=typer.colors.RED)
    )


def note(message: str, *, indent: int = 2) -> None:
    """Plain explanatory text, dim color."""
    pad = " " * indent
    typer.secho(f"{pad}{message}", fg=typer.colors.BRIGHT_BLACK)


def divider() -> None:
    """Full-width rule — used between major sections."""
    typer.secho("═" * WIDTH, fg=typer.colors.BRIGHT_BLUE)


def closing(message: str) -> None:
    """End-of-demo closing line in the banner style."""
    divider()
    typer.secho(f"  {message}", bold=True)
    divider()
