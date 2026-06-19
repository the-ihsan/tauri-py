"""Ensure Playwright browser binaries are installed on the client machine."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

_INSTALL_LOCK = asyncio.Lock()
_APP_BROWSERS_FLAG = "APP_PLAYWRIGHT_BROWSERS"
_PERCENT_RE = re.compile(r"(\d+)%\s+of\b")


class InstallProgress(TypedDict):
    message: str
    percent: int | None


ProgressCallback = Callable[[InstallProgress], None]

def _default_browsers_path() -> Path:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "ms-playwright"
        return Path.home() / "AppData" / "Local" / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _app_browsers_path() -> Path | None:
    raw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if not raw:
        return None
    if os.environ.get(_APP_BROWSERS_FLAG) != "1":
        return None
    return Path(raw)


def _candidate_browsers_paths() -> list[Path]:
    paths: list[Path] = []
    app_path = _app_browsers_path()
    if app_path is not None:
        paths.append(app_path)

    raw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if raw and app_path is None:
        candidate = Path(raw)
        if candidate.exists() or candidate.parent.exists():
            paths.append(candidate)

    default = _default_browsers_path()
    if default not in paths:
        paths.append(default)
    return paths


def _install_browsers_path() -> Path:
    return _app_browsers_path() or _default_browsers_path()


def _chromium_installed_at(browsers_path: Path) -> bool:
    prior = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            return executable.is_file()
    except Exception:
        return False
    finally:
        if prior is None:
            os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
        else:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = prior


def _chromium_installed_sync() -> bool:
    """Return True only when Chromium exists at the path Playwright will use."""
    app_path = _app_browsers_path()
    if app_path is not None:
        # Sidecar sets APP_PLAYWRIGHT_BROWSERS=1 and PLAYWRIGHT_BROWSERS_PATH to
        # the app data dir. A copy in ~/.cache/ms-playwright must not count.
        return _chromium_installed_at(app_path)
    return any(_chromium_installed_at(path) for path in _candidate_browsers_paths())


def _active_browsers_path() -> Path:
    app_path = _app_browsers_path()
    if app_path is not None:
        return app_path
    for path in _candidate_browsers_paths():
        if _chromium_installed_at(path):
            return path
    return _install_browsers_path()


def _playwright_env_for_path(browsers_path: Path) -> dict[str, str]:
    from playwright._impl._driver import get_driver_env

    env = get_driver_env()
    browsers_path.mkdir(parents=True, exist_ok=True)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    return env


def _playwright_env() -> dict[str, str]:
    return _playwright_env_for_path(_active_browsers_path())


def _install_playwright_env() -> dict[str, str]:
    return _playwright_env_for_path(_install_browsers_path())


class _InstallProgressTracker:
    """Turn Playwright install stdout into user-facing progress with overall percent."""

    def __init__(self) -> None:
        self._labels: list[str] = []
        self._current_index = -1
        self._current_percent = 0
        self._completed: set[int] = set()

    def _overall_percent(self) -> int | None:
        if self._current_index < 0:
            return None
        total = max(self._current_index + 1, len(self._completed))
        done = len(self._completed)
        partial = 0.0
        if self._current_index not in self._completed:
            partial = self._current_percent / 100
        return min(99, int((done + partial) / total * 100))

    def _current_label(self) -> str:
        if 0 <= self._current_index < len(self._labels):
            return self._labels[self._current_index]
        return "Downloading browser components…"

    def update(self, line: str) -> InstallProgress:
        if line.startswith("Downloading "):
            self._current_index += 1
            label = line.removesuffix("…").strip()
            self._labels.append(label)
            self._current_percent = 0
            return {
                "message": label,
                "percent": self._overall_percent(),
            }

        match = _PERCENT_RE.search(line)
        if match is not None and self._current_index >= 0:
            self._current_percent = int(match.group(1))
            return {
                "message": self._current_label(),
                "percent": self._overall_percent(),
            }

        if " downloaded to " in line:
            self._completed.add(self._current_index)
            self._current_percent = 100
            name = line.split(" downloaded to ", 1)[0].strip()
            return {
                "message": f"{name} downloaded",
                "percent": self._overall_percent(),
            }

        return {
            "message": line,
            "percent": self._overall_percent(),
        }


def _emit_progress(
    on_progress: ProgressCallback | None,
    message: str,
    *,
    percent: int | None = None,
) -> None:
    if on_progress is None:
        return
    on_progress({"message": message, "percent": percent})


def _run_playwright_cli(
    *args: str,
    on_progress: ProgressCallback | None = None,
) -> subprocess.CompletedProcess[str]:
    from playwright._impl._driver import compute_driver_executable

    node, cli = compute_driver_executable()
    env = _install_playwright_env()
    if on_progress is None:
        return subprocess.run(
            [node, cli, *args],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    proc = subprocess.Popen(
        [node, cli, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    output_lines: list[str] = []
    tracker = _InstallProgressTracker()
    assert proc.stdout is not None
    for line in proc.stdout:
        stripped = line.rstrip()
        if stripped:
            output_lines.append(stripped)
            if on_progress is not None:
                on_progress(tracker.update(stripped))
    returncode = proc.wait()
    combined = "\n".join(output_lines)
    return subprocess.CompletedProcess(
        args=[node, cli, *args],
        returncode=returncode,
        stdout=combined,
        stderr="",
    )


async def chromium_installed() -> bool:
    try:
        return await asyncio.to_thread(_chromium_installed_sync)
    except Exception:
        return False


def _install_chromium_sync(on_progress: ProgressCallback | None = None) -> None:
    _emit_progress(
        on_progress,
        "Starting Chromium download via Playwright…",
        percent=0,
    )

    result = _run_playwright_cli("install", "chromium", on_progress=on_progress)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or "playwright install chromium failed")

    _emit_progress(on_progress, "Verifying Chromium installation…", percent=99)


async def install_chromium(on_progress: ProgressCallback | None = None) -> None:
    """Download Chromium via Playwright; raises on failure."""
    async with _INSTALL_LOCK:
        await asyncio.to_thread(_install_chromium_sync, on_progress)
        if not await chromium_installed():
            raise RuntimeError("Chromium install finished but Playwright cannot find it")
        _emit_progress(on_progress, "Chromium is ready.", percent=100)

async def ensure_playwright_browsers() -> None:
    """Install Chromium on first use if Playwright does not already have it."""
    if await chromium_installed():
        return
    await install_chromium()
