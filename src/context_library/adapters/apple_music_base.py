"""Shared base logic for Apple Music adapters.

This module provides the common functionality for AppleMusicAdapter and
AppleMusicLibraryAdapter, including HTTP client management, track fetching,
and markdown building.
"""

import json
import logging

logger = logging.getLogger(__name__)

HAS_HTTPX = False
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass


class AppleMusicBaseMixin:
    """Mixin providing shared logic for Apple Music adapters.

    Provides HTTP client management, API fetch logic, and track markdown building.
    """

    def _init_httpx_client(self) -> None:
        """Initialize httpx client if available.

        Raises:
            ImportError: If httpx is not installed.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for Apple Music adapters. "
                "Install with: pip install context-library[apple-music]"
            )
        self._client = httpx.Client(timeout=30.0)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if hasattr(self, "_client"):
            self._client.close()
        return False

    def __del__(self) -> None:
        """Cleanup httpx client on deletion."""
        if hasattr(self, "_client"):
            self._client.close()

    def _fetch_tracks(self, api_url: str, api_key: str, since: str | None = None) -> list[dict]:
        """Fetch track list from the macOS helper API.

        Args:
            api_url: Base URL of the helper API
            api_key: Bearer token for authentication
            since: Optional ISO 8601 timestamp for incremental fetch

        Returns:
            List of track dictionaries

        Raises:
            httpx.HTTPStatusError: If the API request fails (auth errors 401/403 propagate immediately)
            httpx.RequestError: If a network error occurs
            json.JSONDecodeError: If the API returns invalid JSON
            ValueError: If the API returns unexpected response schema
        """
        params = {}
        if since:
            params["since"] = since

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = self._client.get(
                f"{api_url}/music/tracks",
                params=params,
                headers=headers,
            )
            response.raise_for_status()

            tracks = response.json()
            if not isinstance(tracks, list):
                raise ValueError(
                    f"macOS helper API '/music/tracks' response must be a list, got {type(tracks).__name__}"
                )

            return tracks

        except httpx.HTTPStatusError as e:
            # Re-raise auth errors immediately for visibility
            if e.response.status_code in (401, 403):
                logger.error(
                    f"Authentication error from Apple Music API: "
                    f"{e.response.status_code} {e.response.text}"
                )
                raise
            logger.error(
                f"HTTP error from Apple Music API /music/tracks: "
                f"{e.response.status_code} {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(
                f"Network error connecting to Apple Music API at {api_url}/music/tracks: {e}"
            )
            raise
        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON response from Apple Music API /music/tracks (possible proxy/HTML response): {e}"
            )
            raise

    @staticmethod
    def _build_track_markdown(
        title: str,
        artist: str | None,
        album: str | None,
        duration_minutes: int | None,
        play_count: int,
        genre: str | None = None,
    ) -> str:
        """Build markdown representation of a track.

        Args:
            title: Track title
            artist: Artist name (optional)
            album: Album name (optional)
            duration_minutes: Duration in minutes (optional)
            play_count: Number of times played
            genre: Genre (optional)

        Returns:
            Markdown string representation of the track
        """
        lines = [f"**{title}**"]

        if artist:
            lines.append(f"- Artist: {artist}")
        if album:
            lines.append(f"- Album: {album}")
        if genre:
            lines.append(f"- Genre: {genre}")
        if duration_minutes is not None:
            lines.append(f"- Duration: {duration_minutes} min")
        lines.append(f"- Play count: {play_count}")

        return "\n".join(lines)
