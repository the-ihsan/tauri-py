from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from bus_message import BusMessage
from facade import Facade
from registry import Registry


class BuilderApp:
    def __init__(self, facade: Facade, registry: Registry) -> None:
        self._facade = facade
        self._registry = registry

    @property
    def registry(self) -> Registry:
        return self._registry

    def on_event(
        self,
        event: str,
        handler: Callable[[Facade, Any], Awaitable[None] | None],
    ) -> None:
        self._registry.on_event(event, handler)

    def on_request(
        self,
        route: str,
        handler: Callable[[Facade, Any], Awaitable[Any] | Any],
    ) -> None:
        self._registry.on_request(route, handler)

    def dispatch(self, event: str, payload: Any) -> None:
        self._facade.dispatch(event, payload)

    async def request(self, route: str, payload: Any) -> Any:
        return await self._facade.request(route, payload)

    def send(self, body: BusMessage) -> None:
        self._facade.send(body)
