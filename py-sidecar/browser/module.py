"""Sidecar request handlers for browser control."""

from __future__ import annotations

import subprocess
from typing import Any

from builder_app import BuilderApp
from facade import Facade

from browser.install import chromium_installed, install_chromium
from browser.instance import BrowserRunInfo
from browser.registry import get_registry


def _headless_from_payload(payload: Any) -> bool:
    if isinstance(payload, dict):
        return bool(payload.get("headless", True))
    return True


def _run_id_from_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        value = payload.get("run_id")
        if value is not None:
            return str(value)
    return None


def _action_from_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        value = payload.get("action")
        if value is not None:
            return str(value)
    raise RuntimeError("control action is required")


def _run_to_dict(info: BrowserRunInfo) -> dict[str, Any]:
    return {
        "ok": True,
        "run_id": info.run_id,
        "running": info.running,
        "headless": info.headless,
        "url": info.url,
        "paused": info.paused,
        "crashed": info.crashed,
    }


def browser_module(app: BuilderApp) -> None:
    registry = get_registry()
    registry.set_emit(lambda event, payload: app.dispatch(event, payload))

    async def browser_launch(_: Facade, payload: Any) -> dict[str, Any]:
        headless = _headless_from_payload(payload)
        info = await registry.launch(headless=headless)
        return _run_to_dict(info)

    async def browser_stop(_: Facade, payload: Any) -> dict[str, Any]:
        run_id = _run_id_from_payload(payload)
        if run_id is None:
            raise RuntimeError("run_id is required")
        info = await registry.stop(run_id=run_id)
        return _run_to_dict(info)

    async def browser_status(_: Facade, payload: Any) -> dict[str, Any]:
        run_id = _run_id_from_payload(payload)
        result = await registry.status(run_id=run_id)
        if isinstance(result, list):
            return {"ok": True, "instances": [_run_to_dict(i) for i in result]}
        return _run_to_dict(result)

    async def browser_recover(_: Facade, payload: Any) -> dict[str, Any]:
        run_id = _run_id_from_payload(payload)
        if run_id is None:
            raise RuntimeError("run_id is required")
        info = await registry.recover(run_id=run_id)
        return _run_to_dict(info)

    async def browser_control(_: Facade, payload: Any) -> dict[str, Any]:
        run_id = _run_id_from_payload(payload)
        if run_id is None:
            raise RuntimeError("run_id is required")
        action = _action_from_payload(payload)
        info = registry.apply_control(run_id=run_id, action=action)
        return _run_to_dict(info)

    async def browser_install_status(_: Facade, _payload: Any) -> dict[str, Any]:
        return {"ok": True, "installed": await chromium_installed()}

    async def browser_install_run(_: Facade, _payload: Any) -> dict[str, Any]:
        def on_progress(progress: dict[str, Any]) -> None:
            app.dispatch("browser.install.progress", progress)

        try:
            await install_chromium(on_progress=on_progress)
        except subprocess.CalledProcessError as exc:
            return {
                "ok": False,
                "installed": await chromium_installed(),
                "error": f"playwright install failed (exit {exc.returncode})",
            }
        except Exception as exc:
            return {
                "ok": False,
                "installed": await chromium_installed(),
                "error": str(exc),
            }
        return {"ok": True, "installed": True}

    app.on_request("browser.launch", browser_launch)
    app.on_request("browser.stop", browser_stop)
    app.on_request("browser.status", browser_status)
    app.on_request("browser.recover", browser_recover)
    app.on_request("browser.control", browser_control)
    app.on_request("browser.install.status", browser_install_status)
    app.on_request("browser.install.run", browser_install_run)
