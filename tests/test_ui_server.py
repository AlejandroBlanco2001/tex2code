from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from latex_ia.models import Profile, Role, Unit, UnitResult
from latex_ia.ui.events import EventBus
from latex_ia.ui.server import create_app


def _make_client(tmp_path: Path) -> tuple[TestClient, EventBus]:
    bus = EventBus()
    profile = Profile(field="ml", model="claude-sonnet-4-6")
    tex_path = tmp_path / "paper.tex"
    tex_path.write_text("\\begin{document}hello\\end{document}")
    app = create_app(bus, tex_path, profile)
    return TestClient(app, raise_server_exceptions=True), bus


class TestIndexRoute:
    def test_returns_200(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "tex2code" in resp.text
        assert "paper.tex" in resp.text

    def test_contains_model_name(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.get("/")
        assert "claude-sonnet-4-6" in resp.text

    def test_contains_sse_connection(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.get("/")
        assert "EventSource" in resp.text or "/events" in resp.text


class TestSourceRoute:
    def test_missing_unit_returns_404(self, tmp_path):
        client, _ = _make_client(tmp_path)
        resp = client.get("/source/no%3Asuch")
        assert resp.status_code == 404

    def test_known_unit_returns_html(self, tmp_path):
        client, bus = _make_client(tmp_path)
        unit = Unit(id="impl:enc", hash="abc", raw="\\begin{implement}x\\end{implement}")
        result = UnitResult(
            role=Role.spec, confidence=0.9, reasoning="r", code_stub="def f(): pass"
        )
        bus.on_unit_processed(unit, result)
        resp = client.get("/source/impl%3Aenc")
        assert resp.status_code == 200
        assert "impl:enc" in resp.text
        assert "implement" in resp.text

    def test_source_route_with_unencoded_colon(self, tmp_path):
        client, bus = _make_client(tmp_path)
        unit = Unit(id="def:prior", hash="xyz", raw="\\newcommand{\\prior}{p_0}")
        result = UnitResult(role=Role.definition, confidence=0.95, reasoning="r")
        bus.on_unit_processed(unit, result)
        resp = client.get("/source/def:prior")
        assert resp.status_code == 200
        assert "def:prior" in resp.text


class TestQuestionsRoutes:
    def _bus_with_question(self, tmp_path) -> tuple[TestClient, EventBus]:
        client, bus = _make_client(tmp_path)
        unit = Unit(id="impl:enc", hash="abc", raw="x")
        result = UnitResult(
            role=Role.spec,
            confidence=0.9,
            reasoning="r",
            open_questions=["What is X?", "What is Y?"],
        )
        bus.on_unit_processed(unit, result)
        return client, bus

    def test_answer_removes_question(self, tmp_path):
        client, bus = self._bus_with_question(tmp_path)
        resp = client.post(
            "/questions/answer",
            data={"unit_id": "impl:enc", "question": "What is X?", "answer": "X = 5"},
        )
        assert resp.status_code == 200
        assert "What is X?" not in bus.questions.get("impl:enc", [])
        assert "What is Y?" in bus.questions.get("impl:enc", [])

    def test_answer_writes_note(self, tmp_path):
        import os

        os.chdir(tmp_path)
        client, bus = self._bus_with_question(tmp_path)
        client.post(
            "/questions/answer",
            data={"unit_id": "impl:enc", "question": "What is X?", "answer": "X = 5"},
        )
        notes = (tmp_path / ".tex2code/notes.md").read_text()
        assert "What is X?" in notes
        assert "X = 5" in notes

    def test_dismiss_removes_question(self, tmp_path):
        client, bus = self._bus_with_question(tmp_path)
        resp = client.post(
            "/questions/dismiss",
            data={"unit_id": "impl:enc", "question": "What is X?"},
        )
        assert resp.status_code == 200
        assert "What is X?" not in bus.questions.get("impl:enc", [])

    def test_answer_response_is_html(self, tmp_path):
        client, bus = self._bus_with_question(tmp_path)
        resp = client.post(
            "/questions/answer",
            data={"unit_id": "impl:enc", "question": "What is X?", "answer": "X = 5"},
        )
        assert "text/html" in resp.headers["content-type"]

    def test_answer_all_questions_returns_empty_state(self, tmp_path):
        client, bus = self._bus_with_question(tmp_path)
        client.post(
            "/questions/answer",
            data={"unit_id": "impl:enc", "question": "What is X?", "answer": "a"},
        )
        resp = client.post(
            "/questions/answer",
            data={"unit_id": "impl:enc", "question": "What is Y?", "answer": "b"},
        )
        assert "No open questions" in resp.text or "impl:enc" not in resp.text
