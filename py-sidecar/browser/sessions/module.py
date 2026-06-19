"""Sidecar request handlers for persisted browser sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from builder_app import BuilderApp
from facade import Facade

from .manager import SessionRunInfo, get_session_manager


def _session_id(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("session_id"):
        return str(payload["session_id"])
    raise ValueError("session_id is required")


def _session_dir(payload: Any) -> Path:
    if isinstance(payload, dict) and payload.get("session_dir"):
        return Path(str(payload["session_dir"]))
    raise ValueError("session_dir is required")


def _run_id(payload: Any) -> str | None:
    if isinstance(payload, dict) and payload.get("run_id"):
        return str(payload["run_id"])
    return None


def _check_url(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("check_url"):
        return str(payload["check_url"])
    raise ValueError("check_url is required")


def _start_url(payload: Any) -> str | None:
    if isinstance(payload, dict) and payload.get("start_url"):
        return str(payload["start_url"])
    return None


def _bool(payload: Any, key: str, default: bool) -> bool:
    if isinstance(payload, dict) and key in payload:
        return bool(payload[key])
    return default


def _run_to_dict(info: SessionRunInfo) -> dict[str, Any]:
    return {
        "ok": True,
        "session_id": info.session_id,
        "run_id": info.run_id,
        "running": info.running,
        "headless": info.headless,
        "url": info.url,
        "crashed": info.crashed,
    }


def sessions_module(app: BuilderApp) -> None:
    manager = get_session_manager()
    manager.set_emit(lambda event, payload: app.dispatch(event, payload))

    async def session_launch(_: Facade, payload: Any) -> dict[str, Any]:
        session_id = _session_id(payload)
        session_dir = _session_dir(payload)
        headless = _bool(payload, "headless", False)
        fresh = _bool(payload, "fresh", False)
        start_url = _start_url(payload)
        info = await manager.launch(
            session_id=session_id,
            session_dir=session_dir,
            headless=headless,
            fresh=fresh,
            start_url=start_url,
        )
        return _run_to_dict(info)

    async def session_stop(_: Facade, payload: Any) -> dict[str, Any]:
        session_id = _session_id(payload)
        session_dir = _session_dir(payload)
        run_id = _run_id(payload)
        info = await manager.stop(
            session_id=session_id,
            session_dir=session_dir,
            run_id=run_id,
        )
        if info is None:
            return {
                "ok": True,
                "session_id": session_id,
                "run_id": run_id or "",
                "running": False,
                "headless": True,
                "url": "",
                "crashed": False,
            }
        return _run_to_dict(info)

    async def session_check(_: Facade, payload: Any) -> dict[str, Any]:
        session_id = _session_id(payload)
        session_dir = _session_dir(payload)
        check_url = _check_url(payload)
        return await manager.check(
            session_id=session_id,
            session_dir=session_dir,
            check_url=check_url,
        )

    app.on_request("session.launch", session_launch)
    app.on_request("session.stop", session_stop)
    app.on_request("session.check", session_check)
