"""EventBus: bridges the watcher thread to the FastAPI SSE stream."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class ActivityEntry:
    unit_id: str
    role: str
    confidence: float
    files: int
    questions_remaining: int


class EventBus:
    """Thread-safe event bus. Watcher calls on_unit_processed(); SSE stream reads from subscribe()."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._rerun_callback: Any = None
        self.activity_log: list[ActivityEntry] = []
        self.questions: dict[str, list[str]] = {}
        self.sources: dict[str, str] = {}

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock, contextlib.suppress(ValueError):
            self._subscribers.remove(q)

    def _push(self, event_type: str, data: str) -> None:
        if not self._loop:
            return
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            self._loop.call_soon_threadsafe(q.put_nowait, (event_type, data))

    def on_unit_processed(self, unit, result) -> None:
        """Called from watcher on_result. Thread-safe — may be called from any thread."""
        entry = ActivityEntry(
            unit_id=unit.id,
            role=str(result.role),
            confidence=result.confidence,
            files=0,
            questions_remaining=len(result.open_questions),
        )
        with self._lock:
            self.activity_log.append(entry)
            self.sources[unit.id] = unit.raw
            if result.open_questions:
                self.questions[unit.id] = list(result.open_questions)
            elif unit.id in self.questions:
                del self.questions[unit.id]

        self._push("activity", unit.id)
        self._push("questions", "")

    def on_question_changed(self, unit_id: str, question: str) -> None:
        """Remove a question (answered or dismissed). Thread-safe."""
        with self._lock:
            if unit_id in self.questions:
                with contextlib.suppress(ValueError):
                    self.questions[unit_id].remove(question)
                if not self.questions[unit_id]:
                    del self.questions[unit_id]
        self._push("questions", "")

    def emit_processing_start(self, count: int) -> None:
        self._push("processing_start", str(count))

    def emit_processing_end(self) -> None:
        self._push("processing_end", "")

    def register_rerun(self, callback: Any) -> None:
        self._rerun_callback = callback

    def request_rerun(self, unit_id: str) -> None:
        if self._rerun_callback:
            self._rerun_callback(unit_id)
