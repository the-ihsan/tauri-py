from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from facade import Facade

EventHandler = Callable[["Facade", Any], Awaitable[None] | None]
RequestHandler = Callable[["Facade", Any], Awaitable[Any] | Any]

EventHandlers = dict[str, list[EventHandler]]
RequestHandlers = dict[str, RequestHandler]


class Registry:
    def __init__(self) -> None:
        self._event_handlers: EventHandlers = {}
        self._request_handlers: RequestHandlers = {}

    def on_event(self, event: str, handler: EventHandler) -> None:
        self._event_handlers.setdefault(event, []).append(handler)

    def on_request(self, route: str, handler: RequestHandler) -> None:
        if route in self._request_handlers:
            raise ValueError(f"Request handler for {route} already exists")
        self._request_handlers[route] = handler

    def clone_sidecar_handlers(self) -> tuple[EventHandlers, RequestHandlers]:
        return (
            {k: list(v) for k, v in self._event_handlers.items()},
            dict(self._request_handlers),
        )
