from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from latex_ia import __version__
from latex_ia.calibration import calibrate
from latex_ia.classifier.gate import gate
from latex_ia.classifier.keyword import KeywordScorer
from latex_ia.classifier.rules import RuleClassifier
from latex_ia.manifest import load as load_manifest
from latex_ia.models import ClassificationResult, ProcessMode, Role
from latex_ia.parser.latex_parser import ParseResult, _parse_source, _resolve_source
from latex_ia.profile import load as load_profile, save as save_profile
from latex_ia.watcher import watch as run_watch

app = typer.Typer(help="Turn the executable parts of a LaTeX paper into a code project.")
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tex2code {__version__}")
        raise typer.Exit()


@app.callback()
def _callback(
    version: bool = typer.Option(None, "--version", callback=_version_callback, is_eager=True),
) -> None:
    pass


def main() -> None:
    app()


_MODE_HELP = (
    "strict = opt-in markers only (default); "
    "scan = rules+keyword on all units, no LLM; "
    "auto = full pipeline including LLM (Milestone 2)"
)


@app.command()
def inspect(
    file: Path = typer.Argument(..., help="Path to the .tex file.", exists=True),  # noqa: B008
    mode: ProcessMode = typer.Option(ProcessMode.strict, "--mode", "-m", help=_MODE_HELP),  # noqa: B008
) -> None:
    """Print the document model for a .tex file."""
    parse_result = ParseResult()
    source = _resolve_source(file, parse_result, depth=0)
    _parse_source(source, parse_result)
    units = parse_result.units

    if parse_result.warnings:
        for w in parse_result.warnings:
            console.print(f"[yellow]warning:[/yellow] {w}")
        console.print()

    if mode == ProcessMode.auto:
        console.print(
            "[yellow]note:[/yellow] LLM tier requires 'tex2code watch'. "
            "Falling back to scan.\n"
        )
        mode = ProcessMode.scan

    manifest = load_manifest()
    rule_clf = RuleClassifier()
    kw_clf = KeywordScorer()

    table = Table(title=f"[bold]{file}[/bold]  —  {len(units)} units  [dim](mode: {mode})[/dim]")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Marked", justify="center")
    table.add_column("Role", style="magenta")
    table.add_column("Conf", justify="right")
    table.add_column("Tier", justify="center")
    table.add_column("Status")

    for unit in units:
        result: ClassificationResult | None = gate(unit, manifest, mode)
        if result is None:
            result = rule_clf.classify(unit)
        if result is None:
            result = kw_clf.classify(unit)

        role = result.role.value if result else Role.unknown.value
        conf = f"{result.confidence:.2f}" if result else "—"
        tier = str(result.tier_used) if result else "—"
        marked = "✓" if unit.marked else "·"
        status = "[dim]skip[/dim]" if (result and result.skipped) else "[green]process[/green]"

        table.add_row(unit.id, marked, role, conf, tier, status)

    console.print(table)


@app.command()
def init(
    file: Path = typer.Argument(..., help="Path to the main .tex file.", exists=True),  # noqa: B008
) -> None:
    """Run domain calibration and create .tex2code/profile.json."""
    profile = calibrate(file, interactive=True)
    save_profile(profile)
    console.print(f"\n[green]✓[/green] Profile saved to [cyan].tex2code/profile.json[/cyan]")
    console.print(f"  field: {profile.field}, model: {profile.model}")


@app.command()
def watch(
    file: Path = typer.Argument(..., help="Path to the main .tex file.", exists=True),  # noqa: B008
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip calibration if profile exists."),  # noqa: B008
) -> None:
    """
    Watch a .tex file and process changed units in the background.

    On first run (no profile.json) the calibration Q&A runs automatically.
    Use 'tex2code init <file>' to re-run calibration at any time.
    """
    profile_path = Path(".tex2code/profile.json")
    if profile_path.exists() and yes:
        profile = load_profile(profile_path)
        console.print(f"[dim]Using existing profile ({profile.field}, {profile.model})[/dim]\n")
    elif profile_path.exists():
        reuse = typer.confirm(
            f"Found .tex2code/profile.json ({load_profile(profile_path).field}). Use it?",
            default=True,
        )
        profile = load_profile(profile_path) if reuse else calibrate(file)
        if not reuse:
            save_profile(profile, profile_path)
    else:
        console.print("[bold]No profile found — running calibration first.[/bold]\n")
        profile = calibrate(file, interactive=True)
        save_profile(profile, profile_path)

    run_watch(file, profile)
