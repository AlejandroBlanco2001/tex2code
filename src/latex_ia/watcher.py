"""Background file watcher — detects .tex saves and processes changed units."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Callable

from rich.console import Console
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from latex_ia.manifest import load as load_manifest, save as save_manifest
from latex_ia.models import Manifest, Profile
from latex_ia.output import write_result
from latex_ia.parser import parse
from latex_ia.worker import process_unit

console = Console()


async def _process_units(
    tex_path: Path,
    profile: Profile,
    manifest: Manifest,
    *,
    on_result: Callable | None = None,
    _completion=None,
) -> None:
    """
    Parse *tex_path*, find changed units, and process them concurrently.

    Changed units are those whose hash differs from the manifest entry.
    Results are written to disk and the manifest is updated after each unit.
    *on_result(unit, result)* is called for each successfully processed unit.
    """
    units = parse(tex_path)
    changed = [
        u
        for u in units
        if u.id not in manifest.entries or manifest.entries[u.id].hash != u.hash
    ]

    if not changed:
        return

    console.print(f"\n[bold cyan]↻[/bold cyan] {len(changed)} changed unit(s)")

    tasks = [process_unit(u, units, profile, _completion=_completion) for u in changed]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for unit, result in zip(changed, results):
        if isinstance(result, Exception):
            console.print(f"  [red]✗[/red] {unit.id}: {result}")
            continue

        written = write_result(unit, result, manifest)
        save_manifest(manifest)

        role_color = {"spec": "green", "result": "yellow"}.get(str(result.role), "white")
        conf = f"{result.confidence:.0%}"
        files_note = f"  [dim]({len(written)} file(s))[/dim]" if written else ""
        console.print(
            f"  [dim]→[/dim] {unit.id} "
            f"[{role_color}]{result.role}[/{role_color}] {conf}{files_note}"
        )

        if result.open_questions:
            console.print(
                f"    [yellow]⚠ {len(result.open_questions)} question(s) → "
                ".tex2code/questions.md[/yellow]"
            )

        if on_result is not None:
            on_result(unit, result)


class _TexHandler(FileSystemEventHandler):
    """
    Thin watchdog handler — debounces .tex saves and delegates to _process_units.

    All processing logic lives in the standalone _process_units coroutine;
    this class only manages the debounce timer and bridges threading → asyncio.
    """

    def __init__(
        self,
        tex_path: Path,
        profile: Profile,
        manifest: Manifest,
        *,
        on_result: Callable | None = None,
        _completion=None,
    ) -> None:
        """Initialise the handler with the document path, profile, and manifest."""
        self._tex_path = tex_path
        self._profile = profile
        self._manifest = manifest
        self._on_result = on_result
        self._completion = _completion
        self._lock = threading.Lock()
        self._debounce_timer: threading.Timer | None = None

    def on_modified(self, event: FileSystemEvent) -> None:
        """Debounce rapid saves — schedule a processing pass 300 ms after the last event."""
        if not str(event.src_path).endswith(".tex"):
            return
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(0.3, self._run_scheduled)
            self._debounce_timer.start()

    def _run_scheduled(self) -> None:
        """Entry point called by the debounce timer; bridges threading → asyncio."""
        asyncio.run(
            _process_units(
                self._tex_path,
                self._profile,
                self._manifest,
                on_result=self._on_result,
                _completion=self._completion,
            )
        )

    def run_now(self) -> None:
        """Run an immediate processing pass (used for the initial scan on startup)."""
        self._run_scheduled()


def watch(
    tex_path: Path,
    profile: Profile,
    *,
    on_result: Callable | None = None,
    _completion=None,
) -> None:
    """
    Start the background watcher loop for *tex_path*.

    Runs until Ctrl-C.  *on_result(unit, result)* is called after each
    successful unit — useful for tests and plugins.
    *_completion* is the litellm.acompletion callable; injectable for tests.
    """
    manifest = load_manifest()
    handler = _TexHandler(
        tex_path,
        profile,
        manifest,
        on_result=on_result,
        _completion=_completion,
    )

    observer = Observer()
    observer.schedule(handler, str(tex_path.parent), recursive=True)
    observer.start()

    console.print(
        f"[bold green]tex2code[/bold green] watching [cyan]{tex_path}[/cyan]  "
        f"[dim](model: {profile.model}, Ctrl-C to stop)[/dim]"
    )

    handler.run_now()

    try:
        while observer.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        console.print("\n[dim]stopped.[/dim]")
