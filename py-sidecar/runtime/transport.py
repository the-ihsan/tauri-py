from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from facade import Facade
from registry import Registry
from req_res import get_message_handler


def _force_utf8_stdio() -> None:
    for stream, kwargs in (
        (sys.stdout, {"encoding": "utf-8", "newline": "\n"}),
        (sys.stdin, {"encoding": "utf-8"}),
        (sys.stderr, {"encoding": "utf-8"}),
    ):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(**kwargs)
            except (ValueError, OSError):
                pass


class Transport:
    def __init__(self, registry: Registry) -> None:
        self._registry = registry
        self._out_queue: asyncio.Queue[str | None] | None = None
        self._pending: set[asyncio.Task] = set()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="transport-io")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_message: Callable[[str], None] | None = None

    def enqueue(self, line: str) -> None:
        if self._loop is None or self._out_queue is None:
            raise RuntimeError("transport not running")
        self._loop.call_soon_threadsafe(self._out_queue.put_nowait, line)

    def _track(self, task: asyncio.Task[None]) -> None:
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def _blocking_read_lines(self, in_queue: asyncio.Queue[str | None]) -> None:
        assert self._loop is not None
        try:
            for line in sys.stdin:
                self._loop.call_soon_threadsafe(in_queue.put_nowait, line)
        finally:
            self._loop.call_soon_threadsafe(in_queue.put_nowait, None)

    async def _read_loop(self) -> None:
        assert self._loop is not None
        assert self._on_message is not None

        in_queue: asyncio.Queue[str | None] = asyncio.Queue()
        threading.Thread(
            target=self._blocking_read_lines,
            args=(in_queue,),
            daemon=True,
        ).start()

        while True:
            line = await in_queue.get()
            if line is None:
                break
            self._on_message(line)

        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
        assert self._out_queue is not None
        await self._out_queue.put(None)

    def _blocking_write(self, line: str) -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    async def _write_loop(self) -> None:
        assert self._loop is not None
        assert self._out_queue is not None
        while True:
            item = await self._out_queue.get()
            if item is None:
                break
            await self._loop.run_in_executor(self._executor, self._blocking_write, item)

    async def _run(self, facade: Facade) -> None:
        self._loop = asyncio.get_running_loop()
        self._out_queue = asyncio.Queue()
        self._on_message = get_message_handler(
            self._registry,
            facade,
            self._loop,
            self._track,
        )
        write_task = asyncio.create_task(self._write_loop())
        facade.dispatch("sidecar_ready", {"status": "ok"})
        try:
            await self._read_loop()
        finally:
            await write_task

    def start(self, facade: Facade) -> None:
        _force_utf8_stdio()
        try:
            asyncio.run(self._run(facade))
        finally:
            self._executor.shutdown(wait=False)
