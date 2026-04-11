"""Exceptions raised by the poller module."""


class PollerNotRunningError(Exception):
    """Raised when attempting to trigger ingest on a stopped poller."""

    pass


class AdapterNotRegisteredError(Exception):
    """Raised when attempting to ingest an adapter that is not registered."""

    pass


class NoSourcesError(Exception):
    """Raised when attempting to ingest an adapter with no sources."""

    pass


class IngestAlreadyInProgressError(Exception):
    """Raised when attempting to ingest an adapter while ingest is already in progress."""

    pass
