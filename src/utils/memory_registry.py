"""
Memory Registry — Atomic read/write interface for docs/agent_memory.json.

Provides thread-safe, atomic file operations to persist learned patterns
and optimization vectors discovered during self-healing cycles.

All writes use a write-then-rename pattern for atomicity (POSIX guarantee).
Reads are non-blocking and gracefully handle missing/corrupt files.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger("memory_registry")

DEFAULT_MEMORY_PATH = Path("docs/agent_memory.json")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_memory(memory_path: Path | str | None = None) -> dict[str, Any]:
    """Load the agent memory registry. Returns empty structure if missing.

    Never raises — returns a valid skeleton on any error.
    """
    path = Path(memory_path) if memory_path else DEFAULT_MEMORY_PATH
    try:
        if not path.exists():
            return _empty_memory()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_memory()
        # Ensure required keys exist
        data.setdefault("learned_patterns", [])
        data.setdefault("optimization_vectors", [])
        data.setdefault("sub_agent_registry", {"agents": []})
        return data
    except (json.JSONDecodeError, OSError, PermissionError) as exc:
        log.warning("Could not load agent memory from %s: %s", path, exc)
        return _empty_memory()


def save_memory(memory: dict[str, Any], memory_path: Path | str | None = None) -> bool:
    """Atomically save the agent memory registry.

    Uses write-to-temp-then-rename for POSIX atomicity.
    Returns True on success, False on failure.
    """
    path = Path(memory_path) if memory_path else DEFAULT_MEMORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    memory["last_updated"] = _now_iso()

    try:
        # Write to a temp file in the same directory (same filesystem = atomic rename)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".agent_memory_",
            suffix=".tmp",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, default=str, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename (POSIX guarantee — overwrites existing file atomically)
        os.rename(tmp_path, path)
        log.debug("Agent memory saved atomically to %s", path)
        return True
    except OSError as exc:
        log.error("Failed to save agent memory: %s", exc)
        # Clean up temp file if it exists
        try:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        return False


def append_learned_pattern(
    category: str,
    title: str,
    description: str,
    fix: str = "",
    tags: list[str] | None = None,
    memory_path: Path | str | None = None,
) -> dict[str, str]:
    """Append a learned pattern to the memory registry.

    This is called automatically by the batch executor when a self-healing
    cycle succeeds (LoopState.AUTONOMOUS_HEALED).

    Returns:
        Dict with 'status' ('SUCCESS' | 'SKIPPED' | 'WRITE_ERROR') and
        'pattern_id' if successful.
    """
    memory = load_memory(memory_path)
    patterns = memory.get("learned_patterns", [])

    # Deduplicate: skip if a pattern with the same category + title exists
    for existing in patterns:
        if existing.get("category") == category and existing.get("title") == title:
            existing["applied_count"] = existing.get("applied_count", 0) + 1
            existing["last_applied_at"] = _now_iso()
            if save_memory(memory, memory_path):
                log.info("Memory registry: updated existing pattern '%s' (applied %d times)", title, existing["applied_count"])
                return {"status": "SUCCESS", "pattern_id": existing.get("id", "unknown")}
            else:
                return {"status": "WRITE_ERROR", "pattern_id": ""}

    # Generate new pattern ID
    pattern_id = f"pattern-{len(patterns) + 1:03d}"

    new_pattern = {
        "id": pattern_id,
        "category": category,
        "title": title,
        "description": description,
        "fix": fix,
        "discovered_at": _now_iso(),
        "applied_count": 1,
        "last_applied_at": _now_iso(),
        "tags": tags or [],
    }

    patterns.append(new_pattern)
    memory["learned_patterns"] = patterns

    if save_memory(memory, memory_path):
        log.info("Memory registry: appended new pattern '%s' (category: %s)", title, category)
        return {"status": "SUCCESS", "pattern_id": pattern_id}
    else:
        return {"status": "WRITE_ERROR", "pattern_id": ""}


def _empty_memory() -> dict[str, Any]:
    """Return an empty memory skeleton."""
    return {
        "description": "Persistent context registry for the agent swarm.",
        "version": "1.0.0",
        "created_at": _now_iso(),
        "last_updated": _now_iso(),
        "learned_patterns": [],
        "optimization_vectors": [],
        "sub_agent_registry": {"agents": []},
    }
