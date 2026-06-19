"""Per-session Playwright browser lifecycle with cookie persistence."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright

from ..install import ensure_playwright_browsers
from ..launch import chromium_launch_kwargs
from ..pages import close_page, open_page
from .storage import storage_path

EmitFn = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class SessionRunInfo:
    session_id: str
    run_id: str
    headless: bool
    url: str
    running: bool
    crashed: bool = False


class SessionRunner:
    def __init__(
        self,
        session_id: str,
        session_dir: Path,
        *,
        emit: EmitFn | None = None,
    ) -> None:
        self.session_id = session_id
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._emit = emit
        self._stack = AsyncExitStack()
        self._playwright: Playwright | None = None
        self._launch_kwargs: dict[str, Any] = chromium_launch_kwargs(headless=False)
        self._run_id: str | None = None
        self._crashed = False
        self._closing = False
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def _is_alive(self) -> bool:
        if self.browser is None:
            return False
        try:
            if not self.browser.is_connected():
                return False
            if self.page is None or self.page.is_closed():
                return False
            return True
        except Exception:
            return False

    @property
    def is_running(self) -> bool:
        return self._is_alive()

    def _on_page_close(self, _: Page) -> None:
        self._schedule_external_close(crashed=False)

    def _on_browser_disconnected(self, _: Browser) -> None:
        self._schedule_external_close(crashed=True)

    def _schedule_external_close(self, *, crashed: bool) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._handle_external_close(crashed=crashed))

    async def _save_storage(self) -> None:
        if self.context is None:
            return
        path = storage_path(self.session_dir)
        try:
            await self.context.storage_state(path=str(path))
        except Exception:
            pass

    async def _handle_external_close(self, *, crashed: bool) -> None:
        if self._closing or self._run_id is None:
            return

        self._closing = True
        try:
            run_id = self._run_id
            headless = bool(self._launch_kwargs.get("headless", True))
            self._crashed = crashed
            await self._save_storage()
            await self._shutdown()
            await self._stack.aclose()
            self._stack = AsyncExitStack()
            self._playwright = None
            self._run_id = None
            if self._emit is not None:
                self._emit(
                    "session.closed",
                    {
                        "ok": True,
                        "session_id": self.session_id,
                        "run_id": run_id,
                        "running": False,
                        "headless": headless,
                        "url": "",
                        "crashed": crashed,
                    },
                )
        finally:
            self._closing = False

    async def launch(
        self, *, headless: bool = False, fresh: bool = False, start_url: str | None = None
    ) -> SessionRunInfo:
        if self.is_running:
            raise RuntimeError("session browser is already running")

        await ensure_playwright_browsers()
        self._launch_kwargs = chromium_launch_kwargs(headless=headless)
        self._run_id = str(uuid.uuid4())
        self._crashed = False

        from playwright.async_api import async_playwright

        self._playwright = await self._stack.enter_async_context(async_playwright())
        await self._launch(fresh=fresh)
        assert self.page is not None and self._run_id is not None

        if start_url:
            await self.page.goto(
                start_url, wait_until="domcontentloaded", timeout=60_000
            )

        return SessionRunInfo(
            session_id=self.session_id,
            run_id=self._run_id,
            headless=headless,
            url=self.page.url,
            running=True,
        )

    async def stop(self, *, run_id: str | None = None) -> SessionRunInfo | None:
        if not self.is_running and self._run_id is None:
            return None

        if run_id is not None and self._run_id != run_id:
            raise RuntimeError(f"unknown session run '{run_id}'")

        self._closing = True
        try:
            stopped_id = self._run_id or ""
            await self._save_storage()
            await self._shutdown()
            await self._stack.aclose()
            self._stack = AsyncExitStack()
            self._playwright = None
            self._run_id = None
            self._crashed = False
            return SessionRunInfo(
                session_id=self.session_id,
                run_id=stopped_id,
                headless=bool(self._launch_kwargs.get("headless", True)),
                url="",
                running=False,
            )
        finally:
            self._closing = False

    async def check(self, *, check_url: str) -> dict[str, Any]:
        info = await self.launch(headless=True, fresh=False)
        assert self.page is not None
        try:
            await self.page.goto(check_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(1.0)
            final_url = self.page.url
            cookies = await self.context.cookies() if self.context else []
            logged_in = _looks_logged_in(check_url, final_url, len(cookies))
            return {
                "ok": True,
                "session_id": self.session_id,
                "run_id": info.run_id,
                "url": final_url,
                "logged_in": logged_in,
                "cookie_count": len(cookies),
            }
        finally:
            await self.stop(run_id=info.run_id)

    async def _launch(self, *, fresh: bool) -> None:
        assert self._playwright is not None
        self.browser = await self._playwright.chromium.launch(**self._launch_kwargs)
        self.browser.on("disconnected", self._on_browser_disconnected)

        context_kwargs: dict[str, Any] = {"locale": "en-US"}
        state_file = storage_path(self.session_dir)
        if not fresh and state_file.is_file():
            context_kwargs["storage_state"] = str(state_file)

        self.context = await self.browser.new_context(**context_kwargs)
        self.page = await open_page(self.context)
        self.page.on("close", self._on_page_close)

    async def _shutdown(self) -> None:
        if self.page is not None:
            try:
                self.page.remove_listener("close", self._on_page_close)
            except Exception:
                pass
            await close_page(self.page)
            self.page = None
        if self.context is not None:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
        if self.browser is not None:
            try:
                self.browser.remove_listener(
                    "disconnected", self._on_browser_disconnected
                )
            except Exception:
                pass
            try:
                if self.browser.is_connected():
                    await self.browser.close()
            except Exception:
                pass
            self.browser = None


def _looks_logged_in(check_url: str, final_url: str, cookie_count: int) -> bool:
    if cookie_count == 0:
        return False

    check_host = urlparse(check_url).netloc.lower()
    final_host = urlparse(final_url).netloc.lower()
    final_path = urlparse(final_url).path.lower()

    if check_host and final_host and check_host not in final_host:
        return False

    login_markers = ("login", "signin", "sign-in", "checkpoint")
    return not any(marker in final_path for marker in login_markers)


class SessionManager:
    def __init__(self) -> None:
        self._runners: dict[str, SessionRunner] = {}
        self._emit: EmitFn | None = None

    def set_emit(self, emit: EmitFn) -> None:
        self._emit = emit

    def _runner(self, session_id: str, session_dir: Path) -> SessionRunner:
        runner = self._runners.get(session_id)
        if runner is None:
            runner = SessionRunner(session_id, session_dir, emit=self._emit)
            self._runners[session_id] = runner
        return runner

    async def launch(
        self,
        *,
        session_id: str,
        session_dir: Path,
        headless: bool = False,
        fresh: bool = False,
        start_url: str | None = None,
    ) -> SessionRunInfo:
        runner = self._runner(session_id, session_dir)
        return await runner.launch(
            headless=headless, fresh=fresh, start_url=start_url
        )

    async def stop(
        self, *, session_id: str, session_dir: Path, run_id: str | None = None
    ) -> SessionRunInfo | None:
        runner = self._runner(session_id, session_dir)
        info = await runner.stop(run_id=run_id)
        if not runner.is_running:
            self._runners.pop(session_id, None)
        return info

    async def check(
        self, *, session_id: str, session_dir: Path, check_url: str
    ) -> dict[str, Any]:
        runner = self._runner(session_id, session_dir)
        try:
            return await runner.check(check_url=check_url)
        finally:
            if not runner.is_running:
                self._runners.pop(session_id, None)


_manager = SessionManager()


def get_session_manager() -> SessionManager:
    return _manager
