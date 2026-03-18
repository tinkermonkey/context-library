"""In-memory cache for context-helper service health status.

Probes the helper's /health endpoint at most once every PROBE_TTL_SECONDS.
Thread-safe; a lock prevents concurrent probes.

Expected helper /health response (best-effort — partial responses are tolerated):

    {
        "status": "ok",
        "collectors": {
            "music":      {"enabled": true,  "healthy": true},
            "reminders":  {"enabled": true,  "healthy": true},
            "messages":   {"enabled": true,  "healthy": true},
            "notes":      {"enabled": true,  "healthy": true},
            "health":     {"enabled": false, "healthy": false},
            "filesystem": {"enabled": false, "healthy": false},
            "obsidian":   {"enabled": false, "healthy": false}
        }
    }

If the helper does not yet implement /health (returns 404 or non-JSON), the
snapshot will still record reachability based on whether the HTTP connection
succeeded at all.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

PROBE_TTL_SECONDS = 30


@dataclass
class CollectorHealth:
    """Health status of a single configured adapter / helper collector."""

    name: str               # adapter_id, e.g. "apple_music:default"
    adapter_type: str       # class name, e.g. "AppleMusicAdapter"
    enabled: bool           # always True — only enabled adapters appear here
    healthy: bool | None    # None = helper didn't report per-collector status
    error: str | None       # error message if healthy is False


@dataclass
class HelperHealthSnapshot:
    """Point-in-time health snapshot for the helper service."""

    reachable: bool
    probed_at: str                              # ISO 8601 UTC
    collectors: list[CollectorHealth] = field(default_factory=list)
    error: str | None = None                    # connection / parse error


class HelperHealthCache:
    """Probes the context-helper /health endpoint and caches the result.

    Call ``get_or_probe()`` from any thread; it returns the cached snapshot
    when fresh, or triggers a new probe when stale.
    """

    def __init__(
        self,
        helper_url: str,
        api_key: str,
        adapters: list,         # list[BaseAdapter]
    ) -> None:
        self._helper_url = helper_url.rstrip("/")
        self._api_key = api_key
        self._adapters = adapters
        self._snapshot: HelperHealthSnapshot | None = None
        self._last_probe: datetime | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_probe(self) -> HelperHealthSnapshot:
        """Return the cached snapshot if still fresh; otherwise re-probe."""
        with self._lock:
            now = datetime.now(timezone.utc)
            stale = (
                self._snapshot is None
                or self._last_probe is None
                or (now - self._last_probe).total_seconds() > PROBE_TTL_SECONDS
            )
            if stale:
                self._snapshot = self._probe()
                self._last_probe = datetime.now(timezone.utc)
            return self._snapshot

    # ------------------------------------------------------------------
    # Internal probe
    # ------------------------------------------------------------------

    def _probe(self) -> HelperHealthSnapshot:
        import httpx  # lazy import — httpx is an optional dependency

        probed_at = datetime.now(timezone.utc).isoformat()

        # Build the collector list from the configured adapters (all enabled).
        collectors = [
            CollectorHealth(
                name=a.adapter_id,
                adapter_type=type(a).__name__,
                enabled=True,
                healthy=None,
                error=None,
            )
            for a in self._adapters
        ]

        try:
            resp = httpx.get(
                f"{self._helper_url}/health",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=5.0,
            )
            resp.raise_for_status()

            # Try to parse per-collector health if the helper reports it.
            try:
                body: Any = resp.json()
            except Exception:
                body = {}

            if isinstance(body, dict):
                raw: Any = body.get("collectors") or {}
                if isinstance(raw, dict):
                    short_map = {self._short_name(c.name): c for c in collectors}
                    for key, info in raw.items():
                        collector = short_map.get(key)
                        if collector is not None and isinstance(info, dict):
                            collector.healthy = bool(info.get("healthy", True))
                            if not collector.healthy:
                                collector.error = (
                                    info.get("error") or info.get("message")
                                )

            return HelperHealthSnapshot(
                reachable=True,
                probed_at=probed_at,
                collectors=collectors,
            )

        except Exception as exc:
            logger.warning(
                "Helper health probe to %s/health failed: %s",
                self._helper_url,
                exc,
            )
            return HelperHealthSnapshot(
                reachable=False,
                probed_at=probed_at,
                collectors=collectors,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _short_name(adapter_id: str) -> str:
        """Map adapter_id to the short collector key used by the helper.

        Examples:
            "apple_music:default"         → "music"
            "apple_reminders:default"     → "reminders"
            "apple_imessage:default"      → "imessage"
            "apple_music_library:default" → "music_library"
            "filesystem:default"          → "filesystem"
        """
        base = adapter_id.split(":")[0]         # e.g. "apple_music"
        return base.removeprefix("apple_")      # e.g. "music"
