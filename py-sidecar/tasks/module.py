"""Sidecar request handlers for the generic task framework."""

from __future__ import annotations

from typing import Any

from builder_app import BuilderApp
from facade import Facade

from tasks.manager import get_task_manager

# Importing task modules registers their task types as a side effect.
import linkedin.posts.task  # noqa: F401,E402


def tasks_module(app: BuilderApp) -> None:
    manager = get_task_manager()
    manager.set_emit(lambda event, payload: app.dispatch(event, payload))

    async def tasks_start(_: Facade, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "invalid payload"}
        return await manager.start(
            run_id=str(payload.get("run_id") or ""),
            task_key=str(payload.get("task") or ""),
            params=payload.get("params") or {},
            inputs=payload.get("inputs") or [],
            resume=bool(payload.get("resume", False)),
        )

    async def tasks_control(_: Facade, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "invalid payload"}
        return manager.control(
            run_id=str(payload.get("run_id") or ""),
            action=str(payload.get("action") or ""),
        )

    app.on_request("tasks.start", tasks_start)
    app.on_request("tasks.control", tasks_control)
