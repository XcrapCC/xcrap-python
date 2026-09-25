"""Sync and async clients for the XCrap API (https://xcrap.cc).

XCrap turns an X/Twitter URL into structured data — or into markdown that is
ready to hand to a language model. There is no authentication of any kind:
construct a client and call a method.

    from xcrap import Xcrap

    with Xcrap() as xcrap:
        tweet = xcrap.tweet("https://x.com/jack/status/20")
        print(tweet.text, xcrap.rate_limit.remaining)

The async client is the same surface with ``await``:

    from xcrap import AsyncXcrap

    async with AsyncXcrap() as xcrap:
        tweet = await xcrap.tweet("https://x.com/jack/status/20")
"""

from __future__ import annotations

import asyncio
import copy
import platform
import re
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Iterator, List, Mapping, Optional, Sequence, Union

import httpx

from .errors import (
    ADVICE,
    XcrapBadRequest,
    XcrapConnectionError,
    XcrapRateLimited,
    error_class_for,
)
from .models import (
    AccountHistory,
    BulkResult,
    DownloadedMedia,
    MediaList,
    RateLimit,
    Replies,
    ResponseMeta,
    SearchResult,
    Thread,
    Timeline,
    TrendsResult,
    Tweet,
    User,
    UserList,
)

__all__ = ["Xcrap", "AsyncXcrap", "VERSION", "DEFAULT_BASE_URL", "FORMATS"]

#: The SDK version, sent in the User-Agent.
VERSION = "1.3.0"

#: The XCrap API.
DEFAULT_BASE_URL = "https://xcrap.cc"

#: Every response format the API speaks.
FORMATS = ("json", "markdown", "yaml", "csv", "html")

#: Statuses worth one retry: they mean "upstream hiccup", not "you asked wrong".
RETRYABLE_STATUSES = frozenset({502, 503, 504})

_FORMAT_ALIASES = {"md": "markdown", "yml": "yaml", "text/markdown": "markdown"}
_FILENAME_RE = re.compile(r'filename="([^"]+)"')


def _date_param(value: Optional[Union[str, datetime]]) -> Optional[str]:
    """A date bound as the API reads it: ISO 8601, or whatever string was given."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _resolve_format(fmt: Optional[str], markdown: bool) -> Optional[str]:
    """Fold the ``format`` and ``markdown`` options into one value.

    ``markdown=True`` is sugar for ``format="markdown"``; an explicit format wins.
    Returns ``None`` when the server default (JSON) should apply.
    """
    if fmt is not None:
        key = str(fmt).strip().lower()
        key = _FORMAT_ALIASES.get(key, key)
        if key not in FORMATS:
            raise XcrapBadRequest(
                f"Unknown format {fmt!r}. Use one of: {', '.join(FORMATS)}.",
                status=400,
                code="bad_request",
            )
        return key
    if markdown:
        return "markdown"
    return None


def _reset_to_datetime(value: Optional[str]) -> Optional[datetime]:
    """``x-ratelimit-reset`` is a Unix timestamp here and a delta elsewhere; take both."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # Anything below ~2001 as an epoch is really "seconds from now".
    epoch = time.time() + number if number < 1_000_000_000 else number
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


class _XcrapBase:
    """Everything the sync and async clients share: URLs, headers, errors."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 30.0,
        retries: int = 1,
        retry_delay: float = 0.5,
        user_agent: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        cache_ttl: float = 0.0,
    ) -> None:
        self.base_url: str = str(base_url).rstrip("/")
        self.timeout: float = timeout
        self.retries: int = retries
        self.retry_delay: float = retry_delay
        self.user_agent: str = user_agent or (
            f"xcrap-python-sdk/{VERSION} (+https://xcrap.cc; "
            f"Python/{platform.python_version()}; httpx/{httpx.__version__})"
        )
        self.extra_headers: Dict[str, str] = dict(headers or {})
        #: Seconds a successful GET response stays in memory; 0 turns it off.
        self.cache_ttl: float = max(float(cache_ttl or 0), 0.0)
        self._cache: Dict[str, Any] = {}

        #: Rate-limit state from the most recent response.
        self.rate_limit: Optional[RateLimit] = None
        #: Provenance of the most recent response.
        self.last_meta: Optional[ResponseMeta] = None

    # ── response cache ──────────────────────────────────────────────────

    def clear_cache(self) -> None:
        """Empty the in-memory response cache (see ``cache_ttl``)."""
        self._cache.clear()

    def _cache_get(self, url: str, method: str, fresh: bool) -> Any:
        if method != "GET" or fresh or self.cache_ttl <= 0:
            return None
        entry = self._cache.get(url)
        if entry is None:
            return None
        expires, value, meta = entry
        if expires < time.monotonic():
            self._cache.pop(url, None)
            return None
        self.last_meta = ResponseMeta(format=meta.format, cache="client", markdown_tokens=meta.markdown_tokens)
        return (copy.deepcopy(value),)

    def _cache_put(self, url: str, method: str, fresh: bool, value: Any) -> None:
        if method != "GET" or fresh or self.cache_ttl <= 0:
            return
        self._cache[url] = (time.monotonic() + self.cache_ttl, copy.deepcopy(value), self.last_meta)
        # Bounded: the oldest entry goes once there are more than 500.
        if len(self._cache) > 500:
            self._cache.pop(next(iter(self._cache)))

    # ── request plumbing ────────────────────────────────────────────────

    def build_url(self, path: str, query: Optional[Mapping[str, Any]] = None) -> str:
        """Build an absolute URL for ``path`` plus ``query``, dropping empty values."""
        url = httpx.URL(self.base_url + path)
        params: List[Any] = []
        for key, value in (query or {}).items():
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                params.append((key, "true" if value else "false"))
            elif isinstance(value, (list, tuple)):
                params.extend((key, str(item)) for item in value)
            else:
                params.append((key, str(value)))
        return str(url.copy_merge_params(params))

    def _request_headers(self, accept: str) -> Dict[str, str]:
        headers = {"user-agent": self.user_agent, "accept": accept}
        headers.update(self.extra_headers)
        return headers

    def _prepare(
        self,
        path: str,
        query: Optional[Mapping[str, Any]],
        fmt: Optional[str],
        fresh: bool,
    ) -> str:
        merged: Dict[str, Any] = dict(query or {})
        if fmt:
            merged["format"] = fmt
        if fresh:
            merged["fresh"] = "1"
        return self.build_url(path, merged)

    def _absorb(self, response: httpx.Response, fmt: Optional[str]) -> None:
        """Record rate-limit and provenance headers from a response."""
        headers = response.headers
        limit = headers.get("x-ratelimit-limit") or headers.get("ratelimit-limit")
        remaining = headers.get("x-ratelimit-remaining") or headers.get("ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset") or headers.get("ratelimit-reset")
        if limit or remaining or reset:
            self.rate_limit = RateLimit(
                limit=int(limit) if limit else None,
                remaining=int(remaining) if remaining else None,
                reset=int(float(reset)) if reset else None,
                reset_at=_reset_to_datetime(reset),
            )
        tokens = headers.get("x-markdown-tokens")
        self.last_meta = ResponseMeta(
            format=fmt or "json",
            cache=headers.get("x-xcrap-cache"),
            markdown_tokens=int(tokens) if tokens else None,
        )

    def _raise(self, response: httpx.Response, url: str) -> None:
        """Turn a non-2xx response into the right typed error and raise it."""
        try:
            payload: Any = response.json()
        except ValueError:
            payload = None
        info = (payload or {}).get("error", {}) if isinstance(payload, dict) else {}
        status = response.status_code
        advice = ADVICE.get(status, ADVICE[500])
        detail = info.get("message") or (response.text or "")[:200] or "Request failed"
        message = f"{status} {info.get('code', response.reason_phrase)}: {detail} — {advice}"

        kwargs: Dict[str, Any] = {
            "status": status,
            "code": info.get("code", "error"),
            "reason": info.get("reason"),
            "hint": info.get("hint"),
            "documentation": info.get("documentation", "https://xcrap.cc/docs"),
            "url": url,
            "body": payload if payload is not None else response.text,
        }
        cls = error_class_for(status)
        if cls is XcrapRateLimited:
            retry_after = response.headers.get("retry-after") or info.get("retry_after_seconds")
            raise XcrapRateLimited(
                message,
                retry_after=int(float(retry_after)) if retry_after else 60,
                reset_at=self.rate_limit.reset_at if self.rate_limit else None,
                budget=info.get("endpoint_budget"),
                **kwargs,
            )
        raise cls(message, **kwargs)

    def _connection_error(self, url: str, exc: Exception) -> XcrapConnectionError:
        return XcrapConnectionError(
            f"Could not reach {self.base_url}: {exc}. Check your network connection and try again.",
            code="connection_failed",
            url=url,
        )

    @staticmethod
    def _bulk_body(urls: Sequence[str]) -> Dict[str, List[str]]:
        items = [str(u) for u in urls]
        if not items:
            raise XcrapBadRequest(
                "bulk() needs at least one URL. Pass a list of post URLs or ids.",
                status=400,
                code="bad_request",
            )
        if len(items) > 50:
            raise XcrapBadRequest(
                f"bulk() accepts at most 50 URLs; you passed {len(items)}. "
                "Split the list into chunks of 50.",
                status=400,
                code="bad_request",
            )
        return {"urls": items}

    @staticmethod
    def _download_result(response: httpx.Response) -> DownloadedMedia:
        match = _FILENAME_RE.search(response.headers.get("content-disposition", ""))
        length = response.headers.get("content-length")
        return DownloadedMedia(
            filename=match.group(1) if match else "xcrap-download",
            content_type=response.headers.get("content-type", "application/octet-stream"),
            content_length=int(length) if length else None,
            content=response.content,
        )


class Xcrap(_XcrapBase):
    """Synchronous client for one XCrap deployment.

    Args:
        base_url: API origin. Defaults to ``https://xcrap.cc``; only change it
            to route requests through a proxy you control.
        timeout: Per-request timeout in seconds.
        retries: Retries for 502/503/504 and transport failures. A 4xx is never
            retried.
        retry_delay: Backoff before a retry, in seconds.
        user_agent: Replaces the default descriptive User-Agent.
        headers: Extra headers sent on every request.
        cache_ttl: Keep successful GET responses in memory for this many
            seconds, so a repeated call costs no request. 0 (default) is off.
        client: Bring your own ``httpx.Client`` (proxies, custom transport…).

    Attributes:
        rate_limit: :class:`~xcrap.models.RateLimit` from the last response.
        last_meta: :class:`~xcrap.models.ResponseMeta` from the last response.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 30.0,
        retries: int = 1,
        retry_delay: float = 0.5,
        user_agent: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        cache_ttl: float = 0.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        super().__init__(
            base_url,
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
            user_agent=user_agent,
            headers=headers,
            cache_ttl=cache_ttl,
        )
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None

    # ── lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "Xcrap":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ── transport ───────────────────────────────────────────────────────

    def _send(
        self,
        url: str,
        *,
        method: str = "GET",
        json_body: Optional[Dict[str, Any]] = None,
        accept: str = "application/json",
    ) -> httpx.Response:
        headers = self._request_headers(accept)
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = self._client.request(
                    method, url, headers=headers, json=json_body, timeout=self.timeout
                )
            except httpx.HTTPError as exc:  # transport failure: nothing was delivered
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise self._connection_error(url, exc) from exc

            # A 4xx means the caller is wrong; retrying changes nothing.
            if response.status_code in RETRYABLE_STATUSES and attempt < self.retries:
                time.sleep(self.retry_delay * (attempt + 1))
                continue
            return response
        raise self._connection_error(url, last_exc or RuntimeError("no response"))

    def _get(
        self,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        fmt: Optional[str] = None,
        fresh: bool = False,
        method: str = "GET",
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = self._prepare(path, query, fmt, fresh)
        hit = self._cache_get(url, method, fresh)
        if hit is not None:
            return hit[0]
        accept = "*/*" if fmt and fmt != "json" else "application/json"
        response = self._send(url, method=method, json_body=json_body, accept=accept)
        if response.status_code >= 400:
            self._absorb(response, fmt)
            self._raise(response, url)
        self._absorb(response, fmt)
        value = response.text if fmt and fmt != "json" else response.json()
        self._cache_put(url, method, fresh, value)
        return value

    # ── endpoints ───────────────────────────────────────────────────────

    def tweet(
        self,
        url: str,
        *,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
        signals: bool = False,
    ) -> Union[Tweet, str]:
        """Fetch a single post.

        Args:
            url: A post URL (x.com, twitter.com, an fx/vx mirror) or a bare id.
            markdown: Return LLM-ready markdown instead of a :class:`Tweet`.
            format: Explicit format — ``json``, ``markdown``, ``yaml``, ``csv``
                or ``html``. Wins over ``markdown``.
            fresh: Bypass the five-day cache and refetch from upstream.
            signals: Add ``signals``: the post's age, whether it is inside For
                You's 48-hour window, whether the author may qualify for X's
                new-author slot, and engagement ratios. Facts from public
                data, not a ranking score.

        Returns:
            A :class:`~xcrap.models.Tweet` with text, author, metrics, media,
            poll, quote, entities and ``meta`` provenance — or a ``str`` when a
            non-JSON format was asked for.

        Raises:
            XcrapNotFound: deleted, private or nonexistent post; ``reason``
                says which when X does.
            XcrapOptedOut: the author opted out of XCrap.
            XcrapRateLimited: 45 requests per minute per IP exceeded.
        """
        fmt = _resolve_format(format, markdown)
        query = {"url": url, **({"signals": "true"} if signals else {})}
        data = self._get("/v1/tweet", query=query, fmt=fmt, fresh=fresh)
        return data if fmt and fmt != "json" else Tweet.from_dict(data)  # type: ignore[return-value]

    def thread(
        self,
        url: str,
        *,
        max_tweets: int = 25,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[Thread, str]:
        """Unroll a thread from any post in it.

        Args:
            url: Any post belonging to the thread.
            max_tweets: Posts to return, 1–100.
            markdown: Return markdown instead of a :class:`Thread`.
            format: Explicit response format.
            fresh: Bypass the cache.

        Returns:
            A :class:`~xcrap.models.Thread` with ``root_id``, ``author``,
            ``count``, ``truncated`` and the ordered ``tweets``.

        Raises:
            XcrapRateLimited: 15 requests per minute per IP exceeded.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get(
            "/v1/thread", query={"url": url, "max_tweets": max_tweets}, fmt=fmt, fresh=fresh
        )
        return data if fmt and fmt != "json" else Thread.from_dict(data)

    def user(
        self,
        handle: str,
        *,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[User, str]:
        """Fetch a profile.

        Args:
            handle: A bare handle, ``@handle``, or a profile URL.
            markdown: Return markdown instead of a :class:`User`.
            format: Explicit response format.
            fresh: Bypass the cache.

        Returns:
            A :class:`~xcrap.models.User` with bio, avatar, banner, join date,
            verification and follower/following/post metrics.

        Raises:
            XcrapNotFound: suspended or nonexistent account.
            XcrapOptedOut: the account opted out of XCrap.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get("/v1/user", query={"handle": handle}, fmt=fmt, fresh=fresh)
        return data if fmt and fmt != "json" else User.from_dict(data)  # type: ignore[return-value]

    def user_tweets(
        self,
        handle: str,
        *,
        count: int = 20,
        cursor: Optional[str] = None,
        exclude_replies: bool = True,
        media_only: bool = False,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[Timeline, str]:
        """Fetch one page of an account's posts, newest first.

        Paging is cursor-based: hand back the ``next_cursor`` you were given to
        get the following page, or use :meth:`iter_user_tweets`.

        Args:
            handle: A bare handle, ``@handle``, or a profile URL.
            count: Posts per page, 1–100.
            cursor: ``next_cursor`` from a previous page.
            exclude_replies: Drop replies to other accounts.
            media_only: Only posts carrying media.
            markdown: Return markdown instead of a :class:`Timeline`.
            format: Explicit response format.
            fresh: Bypass the cache.

        Returns:
            A :class:`~xcrap.models.Timeline` with ``handle``, ``count``,
            ``next_cursor`` and ``tweets``.

        Raises:
            XcrapRateLimited: 15 requests per minute per IP exceeded.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get(
            "/v1/user/tweets",
            query={
                "handle": handle,
                "count": count,
                "cursor": cursor,
                "exclude_replies": "true" if exclude_replies else "false",
                "media_only": "true" if media_only else "false",
            },
            fmt=fmt,
            fresh=fresh,
        )
        return data if fmt and fmt != "json" else Timeline.from_dict(data)

    def iter_user_tweets(
        self,
        handle: str,
        *,
        count: int = 20,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        exclude_replies: bool = True,
        media_only: bool = False,
        fresh: bool = False,
    ) -> Iterator[Tweet]:
        """Walk every page of an account's posts, yielding one post at a time.

        Stops when the API stops handing back a cursor, or after ``limit`` posts.
        JSON only — a paged markdown stream would not be parseable.

        Args:
            handle: A bare handle, ``@handle``, or a profile URL.
            count: Posts per request, 1–100.
            limit: Stop after this many posts. ``None`` means no limit.
            cursor: Start from this cursor instead of the newest post.
            exclude_replies: Drop replies to other accounts.
            media_only: Only posts carrying media.
            fresh: Bypass the cache.

        Yields:
            :class:`~xcrap.models.Tweet` objects, newest first.
        """
        yielded = 0
        while limit is None or yielded < limit:
            page = self.user_tweets(
                handle,
                count=count,
                cursor=cursor,
                exclude_replies=exclude_replies,
                media_only=media_only,
                fresh=fresh,
            )
            assert isinstance(page, Timeline)
            for post in page.tweets:
                yield post
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not page.next_cursor or not page.tweets:
                return
            cursor = page.next_cursor

    def search(
        self,
        query: str,
        *,
        feed: str = "latest",
        since: Optional[Union[str, datetime]] = None,
        until: Optional[Union[str, datetime]] = None,
        cursor: Optional[str] = None,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[SearchResult, str]:
        """Full-text search over X posts, with X's own search operators.

        Args:
            query: What to search for, e.g. ``"from:nasa mars"``.
            feed: ``latest``, ``top``, ``photos`` or ``videos``.
            since: Oldest post to match, as a date string or a datetime.
            until: Newest post to match, as a date string or a datetime.
            cursor: ``next_cursor`` from a previous page.
            markdown: Return markdown instead of a :class:`SearchResult`.
            format: Explicit response format.
            fresh: Bypass the ten-minute cache.

        Returns:
            A :class:`~xcrap.models.SearchResult` with ``tweets`` and
            ``next_cursor``.

        Raises:
            XcrapBadRequest: empty query, unknown feed or unreadable date.
            XcrapRateLimited: 10 requests per 15 minutes per IP exceeded.
            XcrapUpstreamError: 503, search capacity is used up for now.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get(
            "/v1/search",
            query={
                "q": query,
                "feed": feed,
                "since": _date_param(since),
                "until": _date_param(until),
                "cursor": cursor,
            },
            fmt=fmt,
            fresh=fresh,
        )
        return data if fmt and fmt != "json" else SearchResult.from_dict(data)

    def replies(
        self,
        url: str,
        *,
        sort: str = "top",
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[Replies, str]:
        """The direct replies to a post: the single page X serves, no paging.

        Args:
            url: The post's URL or numeric id.
            sort: ``top`` for the most liked first, ``recent`` for the newest first.
            markdown: Return markdown instead of :class:`Replies`.
            format: Explicit response format.
            fresh: Bypass the one-hour cache.

        Returns:
            A :class:`~xcrap.models.Replies` with the post and its ``replies``.

        Raises:
            XcrapNotFound: deleted, private or nonexistent post.
            XcrapRateLimited: 15 requests per minute per IP exceeded.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get(
            "/v1/replies", query={"url": url, "sort": sort}, fmt=fmt, fresh=fresh
        )
        return data if fmt and fmt != "json" else Replies.from_dict(data)

    def followers(
        self,
        handle: str,
        *,
        cursor: Optional[str] = None,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[UserList, str]:
        """One page of the accounts following an account.

        Args:
            handle: A bare handle, ``@handle``, or a profile URL.
            cursor: ``next_cursor`` from a previous page.
            markdown: Return markdown instead of a :class:`UserList`.
            format: Explicit response format.
            fresh: Bypass the one-hour cache.

        Returns:
            A :class:`~xcrap.models.UserList` with ``users`` and ``next_cursor``.

        Raises:
            XcrapRateLimited: 15 requests per minute per IP exceeded.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get(
            "/v1/user/followers", query={"handle": handle, "cursor": cursor}, fmt=fmt, fresh=fresh
        )
        return data if fmt and fmt != "json" else UserList.from_dict(data)

    def following(
        self,
        handle: str,
        *,
        cursor: Optional[str] = None,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[UserList, str]:
        """One page of the accounts an account follows. See :meth:`followers`."""
        fmt = _resolve_format(format, markdown)
        data = self._get(
            "/v1/user/following", query={"handle": handle, "cursor": cursor}, fmt=fmt, fresh=fresh
        )
        return data if fmt and fmt != "json" else UserList.from_dict(data)

    def user_history(
        self,
        handle: str,
        *,
        max_posts: int = 200,
        since: Optional[Union[str, datetime]] = None,
        until: Optional[Union[str, datetime]] = None,
        include_replies: bool = False,
        include_reposts: bool = False,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[AccountHistory, str]:
        """An account's posts in bulk: up to 1,000 in one call, newest first.

        Args:
            handle: A bare handle, ``@handle``, or a profile URL.
            max_posts: Stop after this many posts, 1–1000.
            since: Oldest post to include, as a date string or a datetime.
            until: Newest post to include, as a date string or a datetime.
            include_replies: Include replies to other accounts.
            include_reposts: Include posts the account reposted.
            markdown: Return markdown instead of an :class:`AccountHistory`.
            format: Explicit response format.
            fresh: Bypass the cache.

        Returns:
            An :class:`~xcrap.models.AccountHistory` with ``tweets``,
            ``truncated`` and the window it covers.

        Raises:
            XcrapBadRequest: a date that cannot be read, or since after until.
            XcrapRateLimited: 4 requests per 5 minutes per IP exceeded.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get(
            "/v1/user/history",
            query={
                "handle": handle,
                "max_posts": max_posts,
                "since": _date_param(since),
                "until": _date_param(until),
                "include_replies": "true" if include_replies else "false",
                "include_reposts": "true" if include_reposts else "false",
            },
            fmt=fmt,
            fresh=fresh,
        )
        return data if fmt and fmt != "json" else AccountHistory.from_dict(data)

    def trends(
        self,
        *,
        count: int = 20,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[TrendsResult, str]:
        """Current trending topics.

        Args:
            count: Trends to return, 1–50.
            markdown: Return markdown instead of a :class:`TrendsResult`.
            format: Explicit response format.
            fresh: Bypass the five-minute trends cache.

        Returns:
            A :class:`~xcrap.models.TrendsResult` with ``count`` and a list of
            ``{rank, name, context, posts, url}`` trends.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get("/v1/trends", query={"count": count}, fmt=fmt, fresh=fresh)
        return data if fmt and fmt != "json" else TrendsResult.from_dict(data)

    def media(
        self,
        url: str,
        *,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[MediaList, str]:
        """List every downloadable file attached to a post.

        Args:
            url: A post URL or numeric id.
            markdown: Return markdown instead of a :class:`MediaList`.
            format: Explicit response format.
            fresh: Bypass the cache.

        Returns:
            A :class:`~xcrap.models.MediaList` whose items carry their ``index``,
            ``variants`` and a ready-made ``download_url``.

        Raises:
            XcrapNotFound: the post has no media.
        """
        fmt = _resolve_format(format, markdown)
        data = self._get("/v1/media", query={"url": url}, fmt=fmt, fresh=fresh)
        return data if fmt and fmt != "json" else MediaList.from_dict(data)

    def download_media(
        self, url: str, *, index: int = 0, quality: str = "best"
    ) -> DownloadedMedia:
        """Download one media file's bytes.

        XCrap streams the file straight through from X; nothing is stored.

        Args:
            url: A post URL or numeric id.
            index: Which attachment, in post order.
            quality: ``best`` or ``worst`` video rendition.

        Returns:
            A :class:`~xcrap.models.DownloadedMedia` with ``filename``,
            ``content_type``, ``content_length`` and ``content``. Call
            ``.save()`` to write it to disk.

        Raises:
            XcrapNotFound: no media, or the index is out of range.
        """
        target = self.build_url(
            "/v1/media/download", {"url": url, "index": index, "quality": quality}
        )
        response = self._send(target, accept="*/*")
        if response.status_code >= 400:
            self._absorb(response, None)
            self._raise(response, target)
        self._absorb(response, "binary")
        return self._download_result(response)

    def bulk(
        self,
        urls: Sequence[str],
        *,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[BulkResult, str]:
        """Resolve up to 50 posts in one call.

        Failures are per item: one dead link returns 49 results and one error
        entry rather than failing the batch. Bulk uses a cheaper upstream, so
        posts come back with less detail than :meth:`tweet` gives.

        Args:
            urls: Post URLs or ids, at most 50.
            markdown: Return markdown instead of a :class:`BulkResult`.
            format: Explicit response format.
            fresh: Bypass the cache.

        Returns:
            A :class:`~xcrap.models.BulkResult` with ``requested``, ``succeeded``,
            ``failed`` and per-item ``results``.

        Raises:
            XcrapBadRequest: empty list, or more than 50 urls.
            XcrapRateLimited: 6 requests per 5 minutes per IP exceeded.
        """
        body = self._bulk_body(urls)
        fmt = _resolve_format(format, markdown)
        data = self._get("/v1/bulk", fmt=fmt, fresh=fresh, method="POST", json_body=body)
        return data if fmt and fmt != "json" else BulkResult.from_dict(data)

class AsyncXcrap(_XcrapBase):
    """Asynchronous client for one XCrap deployment.

    Same surface as :class:`Xcrap`, with ``await`` and ``async for``:

        async with AsyncXcrap() as xcrap:
            tweet = await xcrap.tweet("https://x.com/jack/status/20")
            async for post in xcrap.iter_user_tweets("nasa", limit=50):
                print(post.text)

    Args:
        base_url: Deployment to talk to. Defaults to ``https://xcrap.cc``.
        timeout: Per-request timeout in seconds.
        retries: Retries for 502/503/504 and transport failures. A 4xx is never
            retried.
        retry_delay: Backoff before a retry, in seconds.
        user_agent: Replaces the default descriptive User-Agent.
        headers: Extra headers sent on every request.
        cache_ttl: Keep successful GET responses in memory for this many
            seconds, so a repeated call costs no request. 0 (default) is off.
        client: Bring your own ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 30.0,
        retries: int = 1,
        retry_delay: float = 0.5,
        user_agent: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        cache_ttl: float = 0.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(
            base_url,
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
            user_agent=user_agent,
            headers=headers,
            cache_ttl=cache_ttl,
        )
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None

    # ── lifecycle ───────────────────────────────────────────────────────

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "AsyncXcrap":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    # ── transport ───────────────────────────────────────────────────────

    async def _send(
        self,
        url: str,
        *,
        method: str = "GET",
        json_body: Optional[Dict[str, Any]] = None,
        accept: str = "application/json",
    ) -> httpx.Response:
        headers = self._request_headers(accept)
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = await self._client.request(
                    method, url, headers=headers, json=json_body, timeout=self.timeout
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise self._connection_error(url, exc) from exc

            if response.status_code in RETRYABLE_STATUSES and attempt < self.retries:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
                continue
            return response
        raise self._connection_error(url, last_exc or RuntimeError("no response"))

    async def _get(
        self,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        fmt: Optional[str] = None,
        fresh: bool = False,
        method: str = "GET",
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = self._prepare(path, query, fmt, fresh)
        hit = self._cache_get(url, method, fresh)
        if hit is not None:
            return hit[0]
        accept = "*/*" if fmt and fmt != "json" else "application/json"
        response = await self._send(url, method=method, json_body=json_body, accept=accept)
        self._absorb(response, fmt)
        if response.status_code >= 400:
            self._raise(response, url)
        value = response.text if fmt and fmt != "json" else response.json()
        self._cache_put(url, method, fresh, value)
        return value

    # ── endpoints ───────────────────────────────────────────────────────

    async def tweet(
        self,
        url: str,
        *,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
        signals: bool = False,
    ) -> Union[Tweet, str]:
        """Fetch a single post. See :meth:`Xcrap.tweet`."""
        fmt = _resolve_format(format, markdown)
        query = {"url": url, **({"signals": "true"} if signals else {})}
        data = await self._get("/v1/tweet", query=query, fmt=fmt, fresh=fresh)
        return data if fmt and fmt != "json" else Tweet.from_dict(data)  # type: ignore[return-value]

    async def thread(
        self,
        url: str,
        *,
        max_tweets: int = 25,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[Thread, str]:
        """Unroll a thread from any post in it. See :meth:`Xcrap.thread`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get(
            "/v1/thread", query={"url": url, "max_tweets": max_tweets}, fmt=fmt, fresh=fresh
        )
        return data if fmt and fmt != "json" else Thread.from_dict(data)

    async def user(
        self,
        handle: str,
        *,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[User, str]:
        """Fetch a profile. See :meth:`Xcrap.user`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get("/v1/user", query={"handle": handle}, fmt=fmt, fresh=fresh)
        return data if fmt and fmt != "json" else User.from_dict(data)  # type: ignore[return-value]

    async def user_tweets(
        self,
        handle: str,
        *,
        count: int = 20,
        cursor: Optional[str] = None,
        exclude_replies: bool = True,
        media_only: bool = False,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[Timeline, str]:
        """Fetch one page of an account's posts. See :meth:`Xcrap.user_tweets`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get(
            "/v1/user/tweets",
            query={
                "handle": handle,
                "count": count,
                "cursor": cursor,
                "exclude_replies": "true" if exclude_replies else "false",
                "media_only": "true" if media_only else "false",
            },
            fmt=fmt,
            fresh=fresh,
        )
        return data if fmt and fmt != "json" else Timeline.from_dict(data)

    async def iter_user_tweets(
        self,
        handle: str,
        *,
        count: int = 20,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        exclude_replies: bool = True,
        media_only: bool = False,
        fresh: bool = False,
    ) -> AsyncIterator[Tweet]:
        """Walk every page of an account's posts. See :meth:`Xcrap.iter_user_tweets`."""
        yielded = 0
        while limit is None or yielded < limit:
            page = await self.user_tweets(
                handle,
                count=count,
                cursor=cursor,
                exclude_replies=exclude_replies,
                media_only=media_only,
                fresh=fresh,
            )
            assert isinstance(page, Timeline)
            for post in page.tweets:
                yield post
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not page.next_cursor or not page.tweets:
                return
            cursor = page.next_cursor

    async def search(
        self,
        query: str,
        *,
        feed: str = "latest",
        since: Optional[Union[str, datetime]] = None,
        until: Optional[Union[str, datetime]] = None,
        cursor: Optional[str] = None,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[SearchResult, str]:
        """Full-text search over X posts. See :meth:`Xcrap.search`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get(
            "/v1/search",
            query={
                "q": query,
                "feed": feed,
                "since": _date_param(since),
                "until": _date_param(until),
                "cursor": cursor,
            },
            fmt=fmt,
            fresh=fresh,
        )
        return data if fmt and fmt != "json" else SearchResult.from_dict(data)

    async def replies(
        self,
        url: str,
        *,
        sort: str = "top",
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[Replies, str]:
        """The direct replies to a post. See :meth:`Xcrap.replies`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get(
            "/v1/replies", query={"url": url, "sort": sort}, fmt=fmt, fresh=fresh
        )
        return data if fmt and fmt != "json" else Replies.from_dict(data)

    async def followers(
        self,
        handle: str,
        *,
        cursor: Optional[str] = None,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[UserList, str]:
        """One page of the accounts following an account. See :meth:`Xcrap.followers`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get(
            "/v1/user/followers", query={"handle": handle, "cursor": cursor}, fmt=fmt, fresh=fresh
        )
        return data if fmt and fmt != "json" else UserList.from_dict(data)

    async def following(
        self,
        handle: str,
        *,
        cursor: Optional[str] = None,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[UserList, str]:
        """One page of the accounts an account follows. See :meth:`Xcrap.following`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get(
            "/v1/user/following", query={"handle": handle, "cursor": cursor}, fmt=fmt, fresh=fresh
        )
        return data if fmt and fmt != "json" else UserList.from_dict(data)

    async def user_history(
        self,
        handle: str,
        *,
        max_posts: int = 200,
        since: Optional[Union[str, datetime]] = None,
        until: Optional[Union[str, datetime]] = None,
        include_replies: bool = False,
        include_reposts: bool = False,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[AccountHistory, str]:
        """An account's posts in bulk. See :meth:`Xcrap.user_history`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get(
            "/v1/user/history",
            query={
                "handle": handle,
                "max_posts": max_posts,
                "since": _date_param(since),
                "until": _date_param(until),
                "include_replies": "true" if include_replies else "false",
                "include_reposts": "true" if include_reposts else "false",
            },
            fmt=fmt,
            fresh=fresh,
        )
        return data if fmt and fmt != "json" else AccountHistory.from_dict(data)

    async def trends(
        self,
        *,
        count: int = 20,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[TrendsResult, str]:
        """Current trending topics. See :meth:`Xcrap.trends`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get("/v1/trends", query={"count": count}, fmt=fmt, fresh=fresh)
        return data if fmt and fmt != "json" else TrendsResult.from_dict(data)

    async def media(
        self,
        url: str,
        *,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[MediaList, str]:
        """List a post's downloadable files. See :meth:`Xcrap.media`."""
        fmt = _resolve_format(format, markdown)
        data = await self._get("/v1/media", query={"url": url}, fmt=fmt, fresh=fresh)
        return data if fmt and fmt != "json" else MediaList.from_dict(data)

    async def download_media(
        self, url: str, *, index: int = 0, quality: str = "best"
    ) -> DownloadedMedia:
        """Download one media file's bytes. See :meth:`Xcrap.download_media`."""
        target = self.build_url(
            "/v1/media/download", {"url": url, "index": index, "quality": quality}
        )
        response = await self._send(target, accept="*/*")
        self._absorb(response, "binary")
        if response.status_code >= 400:
            self._raise(response, target)
        return self._download_result(response)

    async def bulk(
        self,
        urls: Sequence[str],
        *,
        markdown: bool = False,
        format: Optional[str] = None,
        fresh: bool = False,
    ) -> Union[BulkResult, str]:
        """Resolve up to 50 posts in one call. See :meth:`Xcrap.bulk`."""
        body = self._bulk_body(urls)
        fmt = _resolve_format(format, markdown)
        data = await self._get("/v1/bulk", fmt=fmt, fresh=fresh, method="POST", json_body=body)
        return data if fmt and fmt != "json" else BulkResult.from_dict(data)
