"""Task base classes and the per-run execution context."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from browser.control import RunControl

EmitFn = Callable[[str, dict[str, Any]], None]


@dataclass
class TaskInput:
    """A single input row for a run (distinct from run-level parameters)."""

    input_id: str
    ordinal: int
    data: dict[str, Any] = field(default_factory=dict)
    cursor: dict[str, Any] | None = None
    seen_keys: list[str] = field(default_factory=list)


class TaskContext:
    """Carries run identity + inputs and emits progress events to the host."""

    def __init__(
        self,
        run_id: str,
        task_key: str,
        params: dict[str, Any] | None,
        inputs: list[TaskInput],
        emit: EmitFn | None,
    ) -> None:
        self.run_id = run_id
        self.task_key = task_key
        self.params: dict[str, Any] = params or {}
        self.inputs = inputs
        self._emit = emit

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit is not None:
            self._emit(event, payload)

    def status(
        self,
        status: str,
        *,
        pause_info: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.emit(
            "task.status",
            {
                "run_id": self.run_id,
                "status": status,
                "pause_info": pause_info,
                "error": error,
            },
        )

    def item(
        self,
        input_id: str,
        item_key: str,
        ordinal: int,
        data: dict[str, Any],
    ) -> None:
        self.emit(
            "task.item",
            {
                "run_id": self.run_id,
                "input_id": input_id,
                "item_key": item_key,
                "ordinal": ordinal,
                "data": data,
            },
        )

    def input_status(
        self,
        input_id: str,
        status: str,
        cursor: dict[str, Any] | None = None,
    ) -> None:
        self.emit(
            "task.input_status",
            {
                "run_id": self.run_id,
                "input_id": input_id,
                "status": status,
                "cursor": cursor,
            },
        )

    def log(self, line: str, *, level: str = "info") -> None:
        self.emit(
            "task.log",
            {
                "run_id": self.run_id,
                "ts": time.time(),
                "level": level,
                "line": str(line),
            },
        )

    def progress(self, **metrics: Any) -> None:
        self.emit("task.progress", {"run_id": self.run_id, **metrics})


class BaseTask:
    """Base class for runnable tasks. Subclasses implement :meth:`run`."""

    def __init__(self, ctx: TaskContext) -> None:
        self.ctx = ctx
        self.control = RunControl()

    async def run(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def pause(self) -> None:
        self.control.pause()

    def resume(self) -> None:
        self.control.resume()

    def stop(self) -> None:
        self.control.stop()
