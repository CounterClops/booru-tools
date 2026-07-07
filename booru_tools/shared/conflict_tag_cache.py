import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger


class ConflictTagCache:

    def __init__(self, cache_file: Path) -> None:
        self._cache_file: Path = Path(cache_file)
        self._data: dict[str, dict] = {}
        self._dirty: bool = False

    def load(self) -> None:
        if not self._cache_file.exists():
            logger.debug(f"Conflict tag cache file '{self._cache_file}' not found, starting empty")
            return
        try:
            with open(self._cache_file, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)
            logger.debug(f"Loaded {len(self._data)} conflict tag cache entries from '{self._cache_file}'")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load conflict tag cache from '{self._cache_file}': {exc}")
            self._data = {}

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            logger.debug(f"Saved conflict tag cache ({len(self._data)} entries) to '{self._cache_file}'")
            self._dirty = False
        except OSError as exc:
            logger.warning(f"Failed to save conflict tag cache to '{self._cache_file}': {exc}")

    def get(self, name: str, ttl_hours: int = 0) -> Optional[dict]:
        entry = self._data.get(name.lower())
        if entry is None:
            return None
        if ttl_hours > 0:
            cached_at_str = entry.get("cached_at")
            if not cached_at_str:
                # Old entry without timestamp — evict so it gets re-fetched
                del self._data[name.lower()]
                self._dirty = True
                return None
            try:
                cached_at = datetime.fromisoformat(cached_at_str)
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(tz=timezone.utc) - cached_at).total_seconds() / 3600
                if age_hours > ttl_hours:
                    logger.debug(
                        f"Conflict cache entry for '{name}' is stale "
                        f"({age_hours:.1f}h old, TTL {ttl_hours}h) — evicting"
                    )
                    del self._data[name.lower()]
                    self._dirty = True
                    return None
            except (ValueError, TypeError):
                del self._data[name.lower()]
                self._dirty = True
                return None
        return entry

    def put(self, names: list[str], category: str) -> None:
        if not names:
            return
        now = datetime.now(tz=timezone.utc).isoformat()
        for name in names:
            key = name.lower()
            existing = self._data.get(key)
            if existing is None or existing.get("names") != names or existing.get("category") != category:
                # New entry or names/category changed — set a fresh timestamp
                self._data[key] = {"names": names, "category": category, "cached_at": now}
                self._dirty = True
            elif "cached_at" not in existing:
                # Old-format entry missing timestamp — backfill without resetting age
                self._data[key] = {**existing, "cached_at": now}
                self._dirty = True
            # Otherwise entry is identical — preserve original cached_at

    def __len__(self) -> int:
        return len(self._data)

    @property
    def is_empty(self) -> bool:
        return not self._data
