"""LinkedIn profile posts scraper — Playwright domain logic for one input row.

Adapted to the generic task framework: progress is streamed through a
:class:`tasks.base.TaskContext` and a shared :class:`browser.control.RunControl`
governs pause/resume/stop. Pause means "do not scrape the next post"; when paused
the scraper persists a checkpoint (anchor + next ordinal) so the run can resume
later, even after the app has been closed.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright

from browser.chrome_cdp import (
    ChromeCdpSession,
    chrome_profile_path,
    launch_chrome_cdp,
    shutdown_chrome_cdp,
)
from browser.control import RunControl
from browser.errors import is_recoverable_browser_error
from browser.install import ensure_chrome
from browser.pages import close_page
from browser.sessions.storage import looks_logged_in_for_platform
from modules.tasks.base import TaskContext

from .extractors import EXPAND_TRUNCATED_POSTS_JS, EXTRACT_POSTS_JS, parse_posts
from .scrolling import count_posts_in_dom, scroll_feed_down
from .urls import profile_activity_url

_STAGNANT_ROUNDS_LIMIT = 8
_RECOVER_SETTLE_SEC = 1.0


@dataclass
class ScrapeConfig:
    profile_url: str
    session_dir: Path
    headless: bool = True
    post_count: int | None = None
    start_from: int = 1
    post_matcher: str | None = None
    initial_post_ids: list[str] = field(default_factory=list)
    initial_top_post_id: str | None = None
    resume_from_ordinal: int = 0
    existing_post_ids: set[str] = field(default_factory=set)


class LinkedInPostInputScraper:
    """Scrapes the posts of a single profile, reporting through ``ctx``."""

    def __init__(
        self,
        ctx: TaskContext,
        input_id: str,
        control: RunControl,
        config: ScrapeConfig,
    ) -> None:
        self.ctx = ctx
        self.input_id = input_id
        self.control = control
        self.config = config
        self._stack = AsyncExitStack()
        self._playwright: Playwright | None = None
        self._cdp: ChromeCdpSession | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._activity_url = ""
        self._top_post_id: str | None = config.initial_top_post_id
        self._snapshot_ids: list[str] = list(config.initial_post_ids)
        self._initial_snapshot_ids: set[str] = set(config.initial_post_ids)
        self._seen_ids: set[str] = set(config.existing_post_ids)
        self._matched = 0
        self._ordinal_map: dict[str, int] = {}
        self._next_ordinal = max(config.resume_from_ordinal, 0) + 1
        self._input_done = False

    @property
    def collected(self) -> int:
        return len(self._seen_ids)

    @property
    def matched(self) -> int:
        return self._matched

    def cursor(self) -> dict[str, Any]:
        return {
            "profile_url": self.config.profile_url,
            "initial_top_post_id": self._top_post_id,
            "initial_post_ids": self._snapshot_ids,
            "resume_from_ordinal": max(self._next_ordinal - 1, 0),
            "collected": self.collected,
            "matched": self._matched,
        }

    def _limit_reached(self) -> bool:
        return (
            self.config.post_count is not None
            and self._matched >= self.config.post_count
        )

    async def _pause_point(self) -> bool:
        """Honour pause/stop before scraping the next post. Returns True to exit."""
        if self.control.stopped:
            return True
        if self.control.is_paused:
            cursor = self.cursor()
            self.ctx.status("paused", pause_info=cursor)
            self.ctx.input_status(self.input_id, "paused", cursor)
            self.ctx.log(f"Paused on {self.config.profile_url}")
            stopped = await self.control.wait_if_paused()
            if stopped:
                return True
            self.ctx.status("running")
            self.ctx.input_status(self.input_id, "running", cursor)
            self.ctx.log(f"Resumed {self.config.profile_url}")
        return self.control.stopped

    async def _launch(self) -> None:
        await ensure_chrome()
        from playwright.async_api import async_playwright

        self._playwright = await self._stack.enter_async_context(async_playwright())
        profile_dir = chrome_profile_path(self.config.session_dir)
        self._cdp = await launch_chrome_cdp(
            self._playwright,
            profile_dir=profile_dir,
            headless=self.config.headless,
            fresh=False,
        )
        self.browser = self._cdp.browser
        self.context = self._cdp.context
        self.page = self._cdp.page

    async def _shutdown(self) -> None:
        if self.page is not None:
            await close_page(self.page)
            self.page = None
        self.context = None
        self.browser = None
        await shutdown_chrome_cdp(self._cdp)
        self._cdp = None

    async def _recover_browser(self) -> None:
        await self._shutdown()
        if await self.control.pause_aware_sleep(_RECOVER_SETTLE_SEC):
            return
        await self._launch()
        assert self.page is not None
        await self.page.goto(
            self._activity_url,
            wait_until="domcontentloaded",
            timeout=90_000,
        )
        await self.control.pause_aware_sleep(2.0)

    async def _with_page_retry(self, fn):
        assert self.page is not None
        try:
            return await fn()
        except Exception as exc:
            if not is_recoverable_browser_error(exc):
                raise
            self.ctx.log("Browser crashed — recovering", level="warning")
            await self._recover_browser()
            return await fn()

    async def _looks_logged_in(self) -> bool:
        assert self.page is not None
        cookies = await self.context.cookies() if self.context else []
        return looks_logged_in_for_platform(
            "linkedin",
            check_url=self._activity_url,
            final_url=self.page.url,
            cookies=cookies,
        )

    async def _expand_truncated_posts(self) -> None:
        assert self.page is not None
        await self.page.evaluate(EXPAND_TRUNCATED_POSTS_JS)

    async def _extract_visible_posts(self) -> list[dict[str, Any]]:
        assert self.page is not None
        await self._expand_truncated_posts()
        raw = await self.page.evaluate(EXTRACT_POSTS_JS)
        return parse_posts(raw)

    async def _run_matcher(self, post: dict[str, Any]) -> bool:
        matcher = self.config.post_matcher
        if not matcher or not matcher.strip():
            return True
        assert self.page is not None
        try:
            result = await self.page.evaluate(
                """
                ([code, post]) => {
                  try {
                    const fn = new Function('post', code);
                    return Boolean(fn(post));
                  } catch (e) {
                    return false;
                  }
                }
                """,
                [matcher.strip(), post],
            )
            return bool(result)
        except Exception:
            return False

    async def _snapshot_anchor(self) -> list[str]:
        posts = await self._with_page_retry(self._extract_visible_posts)
        ids = [p["post_id"] for p in posts if p.get("post_id")]
        if not self._top_post_id and ids:
            self._top_post_id = ids[0]

        if not self._initial_snapshot_ids and ids:
            self._snapshot_ids = ids
            self._initial_snapshot_ids = set(ids)
            for idx, pid in enumerate(ids, start=1):
                if pid not in self._ordinal_map:
                    self._ordinal_map[pid] = idx
            self._next_ordinal = max(self._ordinal_map.values(), default=0) + 1
            # Persist the anchor immediately so a later resume can continue.
            self.ctx.input_status(self.input_id, "running", self.cursor())
        elif self.config.initial_post_ids:
            for idx, pid in enumerate(self.config.initial_post_ids, start=1):
                if pid not in self._ordinal_map:
                    self._ordinal_map[pid] = idx
            self._next_ordinal = max(
                self._next_ordinal, max(self._ordinal_map.values(), default=0) + 1
            )

        return ids

    def _eligible_posts(self, posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Posts to process: anchor onward in DOM, skipping new-at-top inserts."""
        if not posts:
            return []

        top_id = self._top_post_id
        if not top_id:
            return posts

        dom_ids = [p.get("post_id") for p in posts]
        try:
            top_idx = dom_ids.index(top_id)
        except ValueError:
            top_idx = 0

        eligible: list[dict[str, Any]] = []
        for idx, post in enumerate(posts):
            post_id = post.get("post_id")
            if not post_id:
                continue
            if idx < top_idx:
                if (
                    post_id not in self._initial_snapshot_ids
                    and post_id not in self._ordinal_map
                    and post_id not in self._seen_ids
                ):
                    continue
            eligible.append(post)
        return eligible

    def _ordinal_for(self, post_id: str) -> int:
        existing = self._ordinal_map.get(post_id)
        if existing is not None:
            return existing
        ordinal = self._next_ordinal
        self._next_ordinal += 1
        self._ordinal_map[post_id] = ordinal
        return ordinal

    async def _process_posts(self, posts: list[dict[str, Any]]) -> int:
        processed = 0
        for post in posts:
            if self.control.stopped:
                break
            if await self._pause_point():
                break
            post_id = post.get("post_id")
            if not post_id or post_id in self._seen_ids:
                continue

            ordinal = self._ordinal_for(post_id)
            if ordinal < self.config.start_from:
                self._seen_ids.add(post_id)
                continue

            matched = await self._run_matcher(post)
            self._seen_ids.add(post_id)
            processed += 1

            data = dict(post)
            data["matched"] = matched
            self.ctx.item(self.input_id, post_id, ordinal, data)

            if matched:
                self._matched += 1
                if self._limit_reached():
                    self._input_done = True
                    break
        return processed

    async def _count_dom_posts(self) -> int:
        assert self.page is not None
        return await count_posts_in_dom(self.page)

    async def _scroll_feed(self) -> None:
        assert self.page is not None
        await scroll_feed_down(self.page, delay=0)
        await self.control.pause_aware_sleep(1.5)

    async def run(self) -> None:
        try:
            await self._launch()
            assert self.page is not None

            self._activity_url = profile_activity_url(self.config.profile_url)
            await self.page.goto(
                self._activity_url,
                wait_until="domcontentloaded",
                timeout=90_000,
            )
            if await self.control.pause_aware_sleep(2.0):
                return

            if not await self._looks_logged_in():
                raise RuntimeError(
                    f"session is not logged in for {self.config.profile_url}"
                )

            await self._snapshot_anchor()

            stagnant_rounds = 0
            last_dom_count = 0

            while not self.control.stopped and not self._input_done:
                if await self._pause_point():
                    break

                posts = await self._with_page_retry(self._extract_visible_posts)
                eligible = self._eligible_posts(posts)
                await self._process_posts(eligible)

                if self.control.stopped or self._input_done:
                    break

                dom_count = await self._with_page_retry(self._count_dom_posts)
                self.ctx.progress(
                    input_id=self.input_id,
                    collected=self.collected,
                    matched=self._matched,
                    dom_count=dom_count,
                    url=self.page.url,
                )

                if dom_count <= last_dom_count:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0
                    last_dom_count = dom_count

                if stagnant_rounds >= _STAGNANT_ROUNDS_LIMIT:
                    break

                if await self._pause_point():
                    break

                await self._with_page_retry(self._scroll_feed)
        finally:
            await self._shutdown()
            await self._stack.aclose()
