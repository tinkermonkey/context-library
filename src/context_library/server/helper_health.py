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

import concurrent.futures
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, cast

logger = logging.getLogger(__name__)

PROBE_TTL_SECONDS = 30


@dataclass
class EndpointDelivery:
    """Delivery state for one endpoint within a multi-endpoint collector."""

    cursor: str | None
    has_more: bool


@dataclass
class CollectorHealth:
    """Health status of a single configured adapter / helper collector."""

    name: str               # adapter_id, e.g. "apple_music:default"
    adapter_type: str       # class name, e.g. "AppleMusicAdapter"
    enabled: bool           # always True — only enabled adapters appear here
    healthy: bool | None    # None = helper didn't report per-collector status
    error: str | None       # error message if healthy is False
    # Delivery progress fields — populated from /status (best-effort)
    cursor: str | None = None       # simple collectors: last delivery cursor
    has_more: bool = False          # simple collectors: more pages exist
    has_pending: bool = False       # simple collectors: stash loaded (PagedCollectors only)
    endpoints: dict[str, EndpointDelivery] | None = None  # multi-endpoint collectors only
    delivery_available: bool = False  # True when _apply_status populated these fields


@dataclass
class HelperHealthSnapshot:
    """Point-in-time health snapshot for the helper service."""

    reachable: bool
    probed_at: str                              # ISO 8601 UTC
    collectors: list[CollectorHealth] = field(default_factory=list)
    error: str | None = None                    # connection / parse error
    watermark: str | None = None                # last successful delivery across all collectors


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
            return cast(HelperHealthSnapshot, self._snapshot)

    # ------------------------------------------------------------------
    # Internal probe
    # ------------------------------------------------------------------

    def _probe(self) -> HelperHealthSnapshot:
        probed_at = datetime.now(timezone.utc).isoformat()

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

        # Fetch /health and /status concurrently to halve worst-case lock hold time.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            health_future = executor.submit(self._get_json, "/health")
            status_future = executor.submit(self._get_json, "/status")

            try:
                health_body = health_future.result()
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

            try:
                status_body = status_future.result()
            except Exception as exc:
                logger.debug("Helper /status probe failed (non-fatal): %s", exc)
                status_body = None

        short_map = {self._short_name(c.name): c for c in collectors}

        if isinstance(health_body, dict):
            raw: Any = health_body.get("collectors") or {}
            if isinstance(raw, dict):
                for key, info in raw.items():
                    collector = short_map.get(key)
                    if collector is not None and isinstance(info, dict):
                        collector.healthy = info.get("status") == "ok"
                        if not collector.healthy:
                            collector.error = (
                                info.get("error") or info.get("message")
                            )

        watermark = self._apply_status(short_map, status_body)
        return HelperHealthSnapshot(
            reachable=True,
            probed_at=probed_at,
            collectors=collectors,
            watermark=watermark,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_json(self, path: str) -> Any:
        """Make an authenticated GET to the helper and return the parsed JSON body.

        Raises on connection errors, HTTP errors, or JSON parse failures.
        """
        import httpx  # lazy import — httpx is an optional dependency

        resp = httpx.get(
            f"{self._helper_url}{path}",
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()

    def _apply_status(
        self,
        short_map: dict[str, CollectorHealth],
        body: Any,
    ) -> str | None:
        """Parse a /status response body and update collector delivery fields.

        Returns the watermark string, or None if the body is absent/invalid.
        """
        if not isinstance(body, dict):
            return None

        watermark: str | None = body.get("watermark")
        raw: Any = body.get("collectors") or {}
        if not isinstance(raw, dict):
            return watermark if isinstance(watermark, str) else None

        for key, info in raw.items():
            collector = short_map.get(key)
            if collector is None or not isinstance(info, dict):
                continue

            collector.delivery_available = True

            endpoints: Any = info.get("endpoints")
            if isinstance(endpoints, dict):
                # Multi-endpoint collector (health, oura) — preserve per-endpoint granularity
                collector.endpoints = {
                    name: EndpointDelivery(
                        cursor=ep.get("cursor"),
                        has_more=bool(ep.get("has_more", False)),
                    )
                    for name, ep in endpoints.items()
                    if isinstance(ep, dict)
                }
            else:
                collector.cursor = info.get("cursor")
                collector.has_more = bool(info.get("has_more", False))
                collector.has_pending = bool(info.get("has_pending", False))

        return watermark if isinstance(watermark, str) else None

    @staticmethod
    def _short_name(adapter_id: str) -> str:
        """Map adapter_id to the short collector key used by the helper.

        Examples:
            "apple_music:default"         → "music"
            "apple_reminders:default"     → "reminders"
            "apple_imessage:default"      → "imessage"
            "apple_music_library:default" → "music_library"
            "obsidian_helper:default"     → "obsidian"
            "filesystem_helper:default"   → "filesystem"
            "oura:default"               → "oura"
        """
        base = adapter_id.split(":")[0]         # e.g. "apple_music"
        _OVERRIDES: dict[str, str] = {
            "apple_music_library": "music",   # combined adapter covers both events + library
            "obsidian_helper": "obsidian",
            "filesystem_helper": "filesystem",
        }
        if base in _OVERRIDES:
            return _OVERRIDES[base]
        return base.removeprefix("apple_")      # e.g. "music"
