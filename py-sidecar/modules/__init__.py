from __future__ import annotations
from collections.abc import Callable

from browser.module import browser_module
from browser.sessions.module import sessions_module
from builder_app import BuilderApp
from facade import Facade
from tasks.module import tasks_module

def test_module(app: BuilderApp) -> None:
    async def ping(_: Facade, payload: dict) -> dict:
        return {"pong": payload.get("message", "")}

    app.on_request("ping", ping)


def test_module_2(app: BuilderApp) -> None:
    async def echo(_: Facade, payload: dict) -> str:
        return str(payload.get("text", ""))

    app.on_request("echo", echo)

    async def on_ready(facade: Facade, _: dict) -> None:
        facade.dispatch("sidecar_ready", {"status": "ok"})

    app.on_event("init", on_ready)





def get_modules() -> list[Callable[[BuilderApp], None]]:
    return [test_module, test_module_2, browser_module, sessions_module, tasks_module]