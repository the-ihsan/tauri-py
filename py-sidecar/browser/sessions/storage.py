"""Persist Playwright storage state (cookies + local storage) per session."""

from __future__ import annotations

from pathlib import Path

STORAGE_FILENAME = "storage_state.json"


def storage_path(session_dir: str | Path) -> Path:
    return Path(session_dir) / STORAGE_FILENAME


def has_storage(session_dir: str | Path) -> bool:
    return storage_path(session_dir).is_file()
