from __future__ import annotations

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


class _TexHandler(FileSystemEventHandler):
    def __init__(
        self,
        tex_path: Path,
        profile: Profile,
        manifest: Manifest,
        *,
        on_result: Callable | None = None,
        _completion=None,
    ):
        self._tex_path = tex_path
        self._profile = profile
        self._manifest = manifest
        self._on_result = on_result
        self._completion = _completion
        self._lock = threading.Lock()
        self._debounce_timer: threading.Timer | None = None

    def on_modified(self, event: FileSystemEvent) -> None:
        if not str(event.src_path).endswith(".tex"):
            return
        # Debounce: wait 300 ms so rapid saves don't trigger multiple passes
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(0.3, self._process)
            self._debounce_timer.start()

    def _process(self) -> None:
        units = parse(self._tex_path)
        changed = [
            u
            for u in units
            if u.id not in self._manifest.entries
            or self._manifest.entries[u.id].hash != u.hash
        ]

        if not changed:
            return

        console.print(f"\n[bold cyan]↻[/bold cyan] {len(changed)} changed unit(s)")

        for unit in changed:
            console.print(f"  [dim]→[/dim] {unit.id}", end=" ")
            try:
                result = process_unit(unit, units, self._profile, _completion=self._completion)
                written = write_result(unit, result, self._manifest)
                save_manifest(self._manifest)

                role_color = {"spec": "green", "result": "yellow"}.get(result.role, "white")
                conf = f"{result.confidence:.0%}"
                files = f"  [dim]({len(written)} file(s))[/dim]" if written else ""
                console.print(
                    f"[{role_color}]{result.role}[/{role_color}] {conf}{files}"
                )

                if result.open_questions:
                    console.print(
                        f"    [yellow]⚠ {len(result.open_questions)} question(s) → "
                        ".tex2code/questions.md[/yellow]"
                    )

                if self._on_result:
                    self._on_result(unit, result)

            except Exception as exc:
                console.print(f"[red]error:[/red] {exc}")


def watch(
    tex_path: Path,
    profile: Profile,
    *,
    on_result: Callable | None = None,
    _completion=None,
) -> None:
    """
    Start the background watcher loop.

    Runs until Ctrl-C. on_result(unit, result) is called after each
    successful unit processing — useful for tests and plugins.
    _completion is the litellm.completion callable; injectable for tests.
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

    # Run an initial pass immediately
    handler._process()

    try:
        while observer.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        console.print("\n[dim]stopped.[/dim]")
