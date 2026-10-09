"""FastAPI application factory for the tex2code browser UI."""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from latex_ia.ui.events import EventBus

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"
_NOTES_MD = Path(".tex2code/notes.md")

_jinja = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def _render(template_name: str, **ctx: object) -> str:
    return _jinja.get_template(template_name).render(**ctx)


def _one_line(html: str) -> str:
    return html.replace("\n", " ").replace("\r", "").strip()


def _render_questions(questions: dict[str, list[str]]) -> str:
    return _one_line(_render("partials/questions_panel.html", question_groups=questions))


def _write_note_md(unit_id: str, question: str, answer: str) -> None:
    """Append a human-readable entry to notes.md."""
    _NOTES_MD.parent.mkdir(parents=True, exist_ok=True)
    with _NOTES_MD.open("a", encoding="utf-8") as f:
        f.write(f"\n## {unit_id}\n\n**Q:** {question}\n**A:** {answer}\n")


async def _event_stream(request: Request, bus: EventBus) -> AsyncGenerator[str, None]:
    yield f"event: questions\ndata: {_render_questions(bus.questions)}\n\n"

    for entry in bus.activity_log:
        html = _render("partials/activity_item.html", entry=entry)
        yield f"event: activity\ndata: {_one_line(html)}\n\n"

    q = bus.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event_type, payload = await asyncio.wait_for(q.get(), timeout=15.0)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue

            if event_type == "activity":
                entry = next(
                    (e for e in reversed(bus.activity_log) if e.unit_id == payload),
                    None,
                )
                if entry:
                    html = _render("partials/activity_item.html", entry=entry)
                    yield f"event: activity\ndata: {_one_line(html)}\n\n"
            elif event_type == "questions":
                html = _render_questions(bus.questions)
                yield f"event: questions\ndata: {html}\n\n"
            elif event_type in ("processing_start", "processing_end"):
                yield f"event: {event_type}\ndata: {payload}\n\n"
    finally:
        bus.unsubscribe(q)


def create_app(bus: EventBus, tex_path: Path, profile) -> FastAPI:
    app = FastAPI(title="tex2code")
    app.state.bus = bus
    app.state.tex_path = tex_path
    app.state.profile = profile

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # ── Main page ──────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        html = _render("index.html", filename=tex_path.name, model=profile.model)
        return HTMLResponse(html)

    # ── SSE ────────────────────────────────────────────────────────────────

    @app.get("/events")
    async def events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _event_stream(request, bus),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Unit split view ────────────────────────────────────────────────────

    @app.get("/unit/{unit_id:path}", response_class=HTMLResponse)
    async def unit_view(unit_id: str) -> HTMLResponse:
        from latex_ia.manifest import load as load_manifest

        raw = bus.sources.get(unit_id, "")
        manifest = load_manifest()
        entry = manifest.entries.get(unit_id)
        role = entry.role.value if entry else "unknown"
        code_content = ""
        test_content = ""
        if entry and entry.code:
            with contextlib.suppress(OSError):
                code_content = Path(entry.code[0]).read_text(encoding="utf-8")
        if entry and entry.tests:
            with contextlib.suppress(OSError):
                test_content = Path(entry.tests[0]).read_text(encoding="utf-8")
        if not raw and not code_content:
            return HTMLResponse(
                "<p class='source-missing'>Unit not available.</p>", status_code=404
            )
        html = _render(
            "partials/unit_split_view.html",
            unit_id=unit_id,
            raw=raw,
            code=code_content,
            tests=test_content,
            role=role,
        )
        return HTMLResponse(html)

    # Keep legacy /source route for backwards compat
    @app.get("/source/{unit_id:path}", response_class=HTMLResponse)
    async def source(unit_id: str) -> HTMLResponse:
        raw = bus.sources.get(unit_id)
        if raw is None:
            return HTMLResponse(
                "<p class='source-missing'>Source not available.</p>", status_code=404
            )
        html = _render("partials/source_panel.html", unit_id=unit_id, raw=raw)
        return HTMLResponse(html)

    # ── Unit marking ───────────────────────────────────────────────────────

    @app.post("/units/{unit_id:path}/mark", response_class=HTMLResponse)
    async def mark_unit(unit_id: str) -> HTMLResponse:
        from latex_ia.ui.marker import mark_unit_in_file

        raw = bus.sources.get(unit_id, "")
        ok = False
        if raw and tex_path.exists():
            ok = mark_unit_in_file(tex_path, raw)
        if ok:
            return HTMLResponse(
                '<span class="badge badge--marked">✓ marked — save the file to process</span>'
            )
        return HTMLResponse('<span class="badge badge--marked">already marked</span>')

    # ── Paper explorer ─────────────────────────────────────────────────────

    @app.get("/paper", response_class=HTMLResponse)
    async def paper_view() -> HTMLResponse:
        from latex_ia.manifest import load as load_manifest
        from latex_ia.parser import parse_document

        parsed = parse_document(tex_path)
        manifest = load_manifest()
        sections: dict[str, list] = defaultdict(list)
        for unit in parsed.units:
            section = " › ".join(unit.section_path) if unit.section_path else ""
            entry = manifest.entries.get(unit.id)
            role = entry.role.value if entry else "unknown"
            sections[section].append(
                {
                    "id": unit.id,
                    "role": role,
                    "marked": unit.marked,
                    "has_code": bool(entry and entry.code),
                    "preview": unit.raw.strip()[:140].replace("\n", " "),
                }
            )
        html = _render("partials/paper_view.html", sections=dict(sections))
        return HTMLResponse(html)

    # ── Notation guide ─────────────────────────────────────────────────────

    @app.get("/notation", response_class=HTMLResponse)
    async def notation_page() -> HTMLResponse:
        from latex_ia.manifest import load as load_manifest
        from latex_ia.parser import parse_document

        parsed = parse_document(tex_path)
        manifest = load_manifest()
        rows = _notation_rows(parsed.units, manifest)
        html = _render("partials/notation_view.html", rows=rows)
        return HTMLResponse(html)

    @app.get("/notation/download")
    async def notation_download() -> FileResponse:
        from latex_ia.manifest import load as load_manifest
        from latex_ia.notation import write_notation_guide
        from latex_ia.parser import parse_document

        parsed = parse_document(tex_path)
        manifest = load_manifest()
        path = write_notation_guide(parsed.units, manifest)
        return FileResponse(str(path), filename="notation.md", media_type="text/markdown")

    # ── Jupyter export ─────────────────────────────────────────────────────

    @app.get("/export/notebook")
    async def export_notebook() -> FileResponse:
        from latex_ia.manifest import load as load_manifest
        from latex_ia.notebook import write_notebook
        from latex_ia.parser import parse_document

        parsed = parse_document(tex_path)
        manifest = load_manifest()
        path = write_notebook(parsed.units, manifest, title=tex_path.stem)
        return FileResponse(
            str(path),
            filename=f"{tex_path.stem}_notebook.ipynb",
            media_type="application/x-ipynb+json",
        )

    # ── Questions ──────────────────────────────────────────────────────────

    @app.post("/questions/answer", response_class=HTMLResponse)
    async def answer_question(
        unit_id: str = Form(...),
        question: str = Form(...),
        answer: str = Form(...),
        rerun: str = Form("false"),
    ) -> HTMLResponse:
        from latex_ia.notes import save_note
        from latex_ia.output import _upsert_questions

        save_note(question, answer, unit_id)
        _write_note_md(unit_id, question, answer)
        bus.on_question_changed(unit_id, question)
        _upsert_questions(unit_id, bus.questions.get(unit_id, []))
        do_rerun = rerun.lower() == "true"
        if do_rerun:
            asyncio.create_task(asyncio.to_thread(bus.request_rerun, unit_id))
        return HTMLResponse(_render("partials/question_saved.html", rerun=do_rerun))

    @app.post("/questions/dismiss", response_class=HTMLResponse)
    async def dismiss_question(
        unit_id: str = Form(...),
        question: str = Form(...),
    ) -> HTMLResponse:
        from latex_ia.notes import save_note
        from latex_ia.output import _upsert_questions

        save_note(question, "", unit_id, dismissed=True)
        bus.on_question_changed(unit_id, question)
        _upsert_questions(unit_id, bus.questions.get(unit_id, []))
        return HTMLResponse(_render("partials/question_dismissed.html"))

    @app.post("/rerun/{unit_id:path}", response_class=HTMLResponse)
    async def rerun(unit_id: str) -> HTMLResponse:
        await asyncio.to_thread(bus.request_rerun, unit_id)
        return HTMLResponse("", status_code=204)

    return app


def _notation_rows(units, manifest) -> list[dict]:
    """Build notation table rows (plain dicts) for the template."""
    rows: list[dict] = []
    seen: set[str] = set()
    for unit in units:
        if not unit.symbols:
            continue
        entry = manifest.entries.get(unit.id)
        role = entry.role.value if entry else "unknown"
        code_file = Path(entry.code[0]).name if (entry and entry.code) else "—"
        section = " › ".join(unit.section_path) if unit.section_path else "—"
        for sym in sorted(unit.symbols):
            if sym in seen:
                continue
            seen.add(sym)
            rows.append(
                {
                    "symbol": sym,
                    "unit_id": unit.id,
                    "role": role,
                    "section": section,
                    "code_file": code_file,
                }
            )
    return rows
