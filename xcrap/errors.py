"""Typed errors for the XCrap SDK.

Every error carries the HTTP status, the API's stable ``code``, and a message
that ends with the action which resolves it — so an error can be shown to a user
or handed to an agent without further translation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Type

__all__ = [
    "XcrapError",
    "XcrapBadRequest",
    "XcrapNotFound",
    "XcrapRateLimited",
    "XcrapOptedOut",
    "XcrapUpstreamError",
    "XcrapConnectionError",
    "error_class_for",
    "ADVICE",
]


class XcrapError(Exception):
    """Base class for every error raised by this SDK.

    Catch this to catch all of them; catch a subclass to handle one case.

    Attributes:
        status: HTTP status the API replied with, or 0 for a transport failure.
        code: Stable machine-readable code, e.g. ``not_found``.
        reason: On a ``not_found`` for a post, why it cannot be read:
            ``post_deleted``, ``author_protected``, ``author_suspended``,
            ``withheld``, ``removed_by_x``, ``age_restricted`` or
            ``unavailable``. ``None`` otherwise.
        hint: The API's own one-line suggestion, when it sent one.
        documentation: Link to the docs page for this failure.
        source: Which upstream produced the failure, when the API said.
        url: The request URL that failed.
        body: The parsed error body, when there was one.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        code: str = "error",
        reason: Optional[str] = None,
        hint: Optional[str] = None,
        documentation: str = "https://xcrap.cc/docs",
        source: Optional[str] = None,
        url: Optional[str] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.reason = reason
        self.hint = hint
        self.documentation = documentation
        self.source = source
        self.url = url
        self.body = body

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class XcrapBadRequest(XcrapError):
    """400 — the request was malformed: a missing or unparseable parameter."""


class XcrapNotFound(XcrapError):
    """404 — the post or account is deleted, suspended, private, or never existed."""


class XcrapRateLimited(XcrapError):
    """429 — the per-endpoint budget for your IP is spent.

    Attributes:
        retry_after: Seconds to wait before retrying, from the ``retry-after``
            header. Sleeping for this long makes the next call succeed.
        reset_at: When the current window rolls over, from ``x-ratelimit-reset``.
        budget: The exhausted budget, e.g. ``{"name": "bulk", "max": 10,
            "window_seconds": 300}``.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: Optional[int] = None,
        reset_at: Optional[datetime] = None,
        budget: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
        self.reset_at = reset_at
        self.budget = budget


class XcrapOptedOut(XcrapError):
    """451 — the account asked to be excluded from XCrap. Nothing will make it work."""


class XcrapUpstreamError(XcrapError):
    """5xx — every upstream refused or timed out. Usually transient; retry shortly."""


class XcrapConnectionError(XcrapError):
    """The request never produced a response: DNS, TLS, socket or timeout failure."""


#: The "and here is what to do about it" half of every error message.
ADVICE: Dict[int, str] = {
    400: (
        "Check the parameter against the API reference at https://xcrap.cc/docs — a tweet "
        "needs a URL or numeric id, a user needs a bare handle."
    ),
    404: (
        "The post or account is deleted, suspended, protected, or never existed. Verify the "
        "URL in a browser; retrying will not help."
    ),
    429: (
        "Wait retry_after seconds (the error carries it) before calling again, or spread "
        "calls out — budgets are per endpoint per IP."
    ),
    451: (
        "This account opted out of XCrap. Do not retry; use a different account or ask them "
        "to opt back in at https://xcrap.cc/opt-out."
    ),
    500: "This is a fault on the XCrap side. It has been reported automatically; retry in a minute.",
    502: (
        "Every upstream source refused. This is usually transient — retry in a minute, or "
        "pass fresh=True to skip a poisoned cache entry."
    ),
    503: "The service is temporarily unavailable. Retry in a minute with backoff.",
    504: (
        "The upstream source did not answer in time. Retry in a minute; a large thread or "
        "timeline can be slow."
    ),
}


def error_class_for(status: int) -> Type[XcrapError]:
    """Map an HTTP status onto the error class that carries the right advice."""
    if status == 400:
        return XcrapBadRequest
    if status == 404:
        return XcrapNotFound
    if status == 429:
        return XcrapRateLimited
    if status == 451:
        return XcrapOptedOut
    if status >= 500:
        return XcrapUpstreamError
    return XcrapError
