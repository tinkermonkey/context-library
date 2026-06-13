"""Shared authentication helpers for server routes."""

import secrets

from fastapi import HTTPException, Request


def require_auth(request: Request) -> None:
    """Enforce Bearer token authentication when CTX_WEBHOOK_SECRET is set.

    If no secret is configured the server is assumed to be operating in a trusted
    network environment and the check is skipped.
    """
    config = request.app.state.config
    if config.webhook_secret:
        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {config.webhook_secret}"
        if not secrets.compare_digest(auth, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing credentials")
