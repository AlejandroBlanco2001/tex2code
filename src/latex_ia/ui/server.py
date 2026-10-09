"""FastAPI application factory for the tex2code browser UI."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
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

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        html = _render(
            "index.html",
            filename=tex_path.name,
            model=profile.model,
        )
        return HTMLResponse(html)

    @app.get("/events")
    async def events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _event_stream(request, bus),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/source/{unit_id:path}", response_class=HTMLResponse)
    async def source(unit_id: str) -> HTMLResponse:
        raw = bus.sources.get(unit_id)
        if raw is None:
            return HTMLResponse(
                "<p class='source-missing'>Source not available.</p>", status_code=404
            )
        html = _render("partials/source_panel.html", unit_id=unit_id, raw=raw)
        return HTMLResponse(html)

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
