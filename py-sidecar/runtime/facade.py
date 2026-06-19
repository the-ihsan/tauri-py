from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from bus_message import BusMessage
from req_res import PENDING_REQUESTS


class Facade:
    def __init__(self, send: Callable[[str], None]) -> None:
        self._send = send

    def dispatch(self, event: str, payload: Any) -> None:
        self._send(BusMessage.event(event, payload).to_json())

    async def request(self, route: str, payload: Any, timeout: float = 10.0) -> Any:
        request_id, future = PENDING_REQUESTS.insert()
        self._send(BusMessage.request(request_id, route, payload).to_json())
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            PENDING_REQUESTS.fail(request_id, f"[PY] #{request_id} timeout")
            raise TimeoutError(f"[PY] #{request_id} timeout") from exc

    def send(self, message: BusMessage) -> None:
        self._send(message.to_json())
