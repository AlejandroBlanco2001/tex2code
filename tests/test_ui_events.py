from __future__ import annotations

import asyncio

from latex_ia.models import Role, Unit, UnitResult
from latex_ia.ui.events import ActivityEntry, EventBus


def _unit(uid: str = "impl:enc") -> Unit:
    return Unit(id=uid, hash="abc", raw="\\begin{implement}x\\end{implement}")


def _result(role: Role = Role.spec, questions: list[str] | None = None) -> UnitResult:
    return UnitResult(
        role=role,
        confidence=0.9,
        reasoning="r",
        code_stub="def f(): pass",
        open_questions=questions or [],
    )


class TestEventBusState:
    def test_on_unit_processed_stores_entry(self):
        bus = EventBus()
        bus.on_unit_processed(_unit("impl:enc"), _result())
        assert len(bus.activity_log) == 1
        entry = bus.activity_log[0]
        assert isinstance(entry, ActivityEntry)
        assert entry.unit_id == "impl:enc"
        assert entry.role == "spec"

    def test_on_unit_processed_stores_source(self):
        bus = EventBus()
        u = _unit("impl:enc")
        bus.on_unit_processed(u, _result())
        assert bus.sources["impl:enc"] == u.raw

    def test_on_unit_processed_with_questions_populates(self):
        bus = EventBus()
        bus.on_unit_processed(_unit(), _result(questions=["What is X?", "What is Y?"]))
        assert bus.questions[_unit().id] == ["What is X?", "What is Y?"]

    def test_on_unit_processed_empty_questions_removes(self):
        bus = EventBus()
        uid = "impl:enc"
        bus.on_unit_processed(_unit(uid), _result(questions=["Q?"]))
        assert uid in bus.questions
        bus.on_unit_processed(_unit(uid), _result(questions=[]))
        assert uid not in bus.questions

    def test_on_question_changed_removes_question(self):
        bus = EventBus()
        uid = "impl:enc"
        bus.on_unit_processed(_unit(uid), _result(questions=["Q1", "Q2"]))
        bus.on_question_changed(uid, "Q1")
        assert bus.questions[uid] == ["Q2"]

    def test_on_question_changed_removes_group_when_empty(self):
        bus = EventBus()
        uid = "impl:enc"
        bus.on_unit_processed(_unit(uid), _result(questions=["Q1"]))
        bus.on_question_changed(uid, "Q1")
        assert uid not in bus.questions

    def test_on_question_changed_unknown_unit_is_noop(self):
        bus = EventBus()
        bus.on_question_changed("no:such", "Q?")  # must not raise

    def test_on_question_changed_unknown_question_is_noop(self):
        bus = EventBus()
        uid = "impl:enc"
        bus.on_unit_processed(_unit(uid), _result(questions=["Q1"]))
        bus.on_question_changed(uid, "not there")
        assert bus.questions[uid] == ["Q1"]


class TestEventBusSubscription:
    def test_subscribe_adds_queue(self):
        bus = EventBus()
        q = bus.subscribe()
        assert q in bus._subscribers

    def test_unsubscribe_removes_queue(self):
        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        assert q not in bus._subscribers

    def test_unsubscribe_missing_is_noop(self):
        bus = EventBus()
        import asyncio as _asyncio

        q: _asyncio.Queue = _asyncio.Queue()
        bus.unsubscribe(q)  # must not raise

    def test_push_without_loop_does_nothing(self):
        bus = EventBus()
        bus.subscribe()
        bus._push("activity", "x")  # no loop set — must not raise


class TestEventBusPush:
    def test_push_delivers_to_subscribers(self):
        async def _run():
            bus = EventBus()
            bus.set_loop(asyncio.get_running_loop())
            q = bus.subscribe()
            bus._push("activity", "hello")
            event_type, data = await asyncio.wait_for(q.get(), timeout=1.0)
            assert event_type == "activity"
            assert data == "hello"

        asyncio.run(_run())

    def test_on_unit_processed_pushes_activity_and_questions(self):
        async def _run():
            bus = EventBus()
            bus.set_loop(asyncio.get_running_loop())
            q = bus.subscribe()
            bus.on_unit_processed(_unit(), _result())
            # Expect two events: "activity" then "questions"
            events = []
            for _ in range(2):
                et, _ = await asyncio.wait_for(q.get(), timeout=1.0)
                events.append(et)
            assert "activity" in events
            assert "questions" in events

        asyncio.run(_run())
