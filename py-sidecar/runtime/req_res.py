from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any

from bus_message import BusMessage
from error_log import error_log
from registry import Registry

if TYPE_CHECKING:
    from facade import Facade


class RequestStates:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._counter = 0

    def insert(self) -> tuple[str, asyncio.Future[Any]]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        request_id = str(self._counter)
        self._counter += 1
        self._pending[request_id] = future
        return request_id, future

    def respond(self, request_id: str, value: Any) -> None:
        future = self._pending.pop(request_id, None)
        if future is not None and not future.done():
            future.set_result(value)

    def fail(self, request_id: str, error: str) -> None:
        future = self._pending.pop(request_id, None)
        if future is not None and not future.done():
            future.set_exception(RuntimeError(error))


PENDING_REQUESTS = RequestStates()


async def _run_handler(handler: Callable, facade: Facade, payload: Any) -> Any:
    if asyncio.iscoroutinefunction(handler):
        return await handler(facade, payload)
    return handler(facade, payload)


def get_message_handler(
    registry: Registry,
    facade: Facade,
    loop: asyncio.AbstractEventLoop,
    track: Callable[[asyncio.Task[None]], None] | None = None,
) -> Callable[[str], None]:
    event_handlers, request_handlers = registry.clone_sidecar_handlers()

    def spawn(coro: Coroutine[Any, Any, Any]) -> None:
        task = loop.create_task(coro)
        if track is not None:
            track(task)

    def on_message(line: str) -> None:
        line = line.strip()
        if not line:
            return

        try:
            msg = BusMessage.from_json(line)
        except (json.JSONDecodeError, KeyError) as exc:
            error_log(f"[PY] invalid json: {line!r} ({exc})")
            return

        if msg.kind == "event":
            handlers = event_handlers.get(msg.route, [])
            if not handlers:
                error_log(f"[PY] no handler for event: {msg.route}")
                return
            for handler in handlers:
                spawn(_run_handler(handler, facade, msg.payload))
            return

        if msg.kind == "request":
            handler = request_handlers.get(msg.route)
            if handler is None:
                error_log(f"[PY] no handler for request: {msg.route}")
                return

            async def handle_request() -> None:
                try:
                    result = await _run_handler(handler, facade, msg.payload)
                    facade.send(msg.to_response(result))
                except Exception as exc:
                    error_log(f"[PY] request handler error: {exc}")
                    facade.send(msg.to_response({"error": str(exc)}))

            spawn(handle_request())
            return

        if msg.kind == "response":
            if not msg.id:
                error_log("[PY] response message has no id")
                return
            PENDING_REQUESTS.respond(msg.id, msg.payload)
            return

        error_log(f"[PY] unknown message kind: {msg.kind}")

    return on_message
