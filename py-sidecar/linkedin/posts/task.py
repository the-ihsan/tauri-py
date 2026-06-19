"""LinkedIn posts scraper task: iterates input rows (profiles) for a run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tasks.base import BaseTask, TaskContext
from tasks.registry import register_task

from .scraper import LinkedInPostInputScraper, ScrapeConfig

TASK_KEY = "linkedin.posts_scraper"


def _optional_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        result = int(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def _profile_url(data: dict[str, Any]) -> str:
    return str(data.get("profile_url") or data.get("url") or "").strip()


class LinkedInPostsTask(BaseTask):
    async def run(self) -> None:
        params = self.ctx.params
        session_dir_raw = str(params.get("session_dir") or "").strip()
        if not session_dir_raw:
            raise RuntimeError("a session is required — select one before starting")
        session_dir = Path(session_dir_raw)

        headless = bool(params.get("headless", True))
        post_count = _optional_int(params.get("post_count"))
        start_from = _optional_int(params.get("start_from")) or 1
        post_matcher = params.get("post_matcher") or None

        if not self.ctx.inputs:
            raise RuntimeError("no input rows provided")

        for inp in self.ctx.inputs:
            if self.control.stopped:
                break

            profile_url = _profile_url(inp.data)
            if not profile_url:
                self.ctx.input_status(inp.input_id, "failed", None)
                self.ctx.log(
                    f"Input #{inp.ordinal + 1}: missing profile_url", level="error"
                )
                continue

            cursor = inp.cursor or {}
            config = ScrapeConfig(
                profile_url=profile_url,
                session_dir=session_dir,
                headless=headless,
                post_count=post_count,
                start_from=start_from,
                post_matcher=post_matcher,
                initial_post_ids=list(cursor.get("initial_post_ids") or []),
                initial_top_post_id=cursor.get("initial_top_post_id"),
                resume_from_ordinal=int(cursor.get("resume_from_ordinal") or 0),
                existing_post_ids=set(inp.seen_keys or []),
            )

            self.ctx.input_status(inp.input_id, "running", cursor or None)
            self.ctx.log(f"Scraping {profile_url}")

            scraper = LinkedInPostInputScraper(
                self.ctx, inp.input_id, self.control, config
            )
            try:
                await scraper.run()
            except Exception as exc:  # noqa: BLE001 - record per-input failure, continue
                self.ctx.input_status(inp.input_id, "failed", scraper.cursor())
                self.ctx.log(f"Failed {profile_url}: {exc}", level="error")
                continue

            if self.control.stopped:
                self.ctx.input_status(inp.input_id, "stopped", scraper.cursor())
                break

            self.ctx.input_status(inp.input_id, "done", scraper.cursor())
            self.ctx.log(
                f"Finished {profile_url}: {scraper.collected} posts "
                f"({scraper.matched} matched)"
            )


register_task(TASK_KEY, lambda ctx: LinkedInPostsTask(ctx))
