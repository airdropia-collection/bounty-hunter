"""
Generic persistent state with TTL-based expiry.

Used for:
- Bounty dedup (don't re-analyze bounties we've already seen)
- Finding dedup (don't re-report the same vuln)
- Submission tracking (which reports are pending/accepted/paid)

Format (JSON file at ``state/<name>.json``):

    {
      "items": {
        "<id>": {
          "added_at": "2026-07-15T...",
          "status": "seen",  # or "analyzed", "submitted", "paid", etc.
          "data": {...}      # arbitrary per-item payload
        }
      },
      "updated_at": "2026-07-15T..."
    }
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.utils.logger import get_logger

log = get_logger("state")

DEFAULT_STATE_DIR = Path("state")
DEFAULT_TTL_HOURS = 24 * 7  # 1 week


class State:
    """Persistent key-value store with TTL-based expiry.

    Each State instance manages one JSON file under ``state/``.
    Thread-safe for sequential use (not for concurrent multi-process).
    """

    def __init__(
        self,
        name: str,
        state_dir: Path | str = DEFAULT_STATE_DIR,
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ):
        """
        Args:
            name: filename without extension (e.g., "bounties_seen")
            state_dir: directory to store state files
            ttl_hours: items older than this are considered expired
        """
        self.name = name
        self.path = Path(state_dir) / f"{name}.json"
        self.ttl = timedelta(hours=ttl_hours)
        self._data: Dict[str, Any] = self._load()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"items": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("could not parse %s, starting fresh: %s", self.path, exc)
            return {"items": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.path.write_text(
                json.dumps(self._data, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            log.error("could not write state file %s: %s", self.path, exc)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def has(self, key: str) -> bool:
        """Return True if ``key`` exists and is not expired."""
        entry = self._data.get("items", {}).get(key)
        if not entry:
            return False
        try:
            ts = datetime.fromisoformat(entry["added_at"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - ts
            if age > self.ttl:
                return False
            return True
        except Exception:  # noqa: BLE001
            return False

    def get(self, key: str) -> Optional[Any]:
        """Return the data payload for ``key``, or None if not present/expired."""
        if not self.has(key):
            return None
        return self._data["items"][key].get("data")

    def add(
        self,
        key: str,
        data: Any = None,
        status: str = "seen",
    ) -> None:
        """Add or update an item."""
        items = self._data.setdefault("items", {})
        items[key] = {
            "added_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "data": data,
        }
        self._save()
        log.debug("state[%s] added: %s (status=%s)", self.name, key, status)

    def update_status(self, key: str, status: str, data: Any = None) -> bool:
        """Update the status of an existing item. Returns False if not found."""
        items = self._data.get("items", {})
        if key not in items:
            return False
        items[key]["status"] = status
        if data is not None:
            items[key]["data"] = data
        items[key]["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        log.debug("state[%s] updated: %s -> %s", self.name, key, status)
        return True

    def filter_unseen(self, keys: list[str]) -> list[str]:
        """Return only the keys that are not already in state (or expired)."""
        return [k for k in keys if not self.has(k)]

    def prune(self) -> int:
        """Remove all expired entries. Returns count pruned."""
        now = datetime.now(timezone.utc)
        items = self._data.get("items", {})
        before = len(items)
        kept = {}
        for key, entry in items.items():
            try:
                ts = datetime.fromisoformat(entry["added_at"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if now - ts <= self.ttl:
                    kept[key] = entry
            except Exception:  # noqa: BLE001
                kept[key] = entry  # keep unparseable
        pruned = before - len(kept)
        self._data["items"] = kept
        if pruned:
            self._save()
            log.info("state[%s] pruned %d expired entries", self.name, pruned)
        return pruned

    def count(self) -> int:
        """Return total number of items (including expired)."""
        return len(self._data.get("items", {}))

    def count_by_status(self) -> Dict[str, int]:
        """Return count of items grouped by status."""
        counts: Dict[str, int] = {}
        for entry in self._data.get("items", {}).values():
            status = entry.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def all_items(self) -> Dict[str, Any]:
        """Return all items (raw). For debugging/reporting."""
        return dict(self._data.get("items", {}))
