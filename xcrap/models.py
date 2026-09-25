"""Dataclasses mirroring the XCrap response shapes.

These mirror ``src/modules/shape.js`` on the server, which is the single source
of truth for the API contract. Every model is built with :meth:`from_dict`,
which tolerates missing keys so a field added upstream never breaks a client,
and keeps the untouched payload in ``raw`` so nothing is ever lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "TweetMetrics",
    "UserMetrics",
    "User",
    "MediaVariant",
    "MediaItem",
    "MediaListItem",
    "MediaList",
    "PollOption",
    "Poll",
    "Entity",
    "Visibility",
    "Signals",
    "EngagementMix",
    "Tweet",
    "Thread",
    "Timeline",
    "SearchResult",
    "Replies",
    "UserList",
    "AccountHistory",
    "Trend",
    "TrendsResult",
    "BulkItem",
    "BulkResult",
    "RateLimit",
    "ResponseMeta",
    "DownloadedMedia",
]


def _get(data: Optional[Dict[str, Any]], key: str, default: Any = None) -> Any:
    if not isinstance(data, dict):
        return default
    value = data.get(key, default)
    return default if value is None else value


@dataclass
class TweetMetrics:
    """Engagement counts. Any of them can be ``None`` when the upstream withheld it."""

    likes: Optional[int] = None
    retweets: Optional[int] = None
    replies: Optional[int] = None
    quotes: Optional[int] = None
    bookmarks: Optional[int] = None
    views: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "TweetMetrics":
        data = data or {}
        return cls(
            likes=data.get("likes"),
            retweets=data.get("retweets"),
            replies=data.get("replies"),
            quotes=data.get("quotes"),
            bookmarks=data.get("bookmarks"),
            views=data.get("views"),
        )


@dataclass
class UserMetrics:
    """Profile counters."""

    posts: Optional[int] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    likes: Optional[int] = None
    media: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "UserMetrics":
        data = data or {}
        return cls(
            posts=data.get("posts"),
            followers=data.get("followers"),
            following=data.get("following"),
            likes=data.get("likes"),
            media=data.get("media"),
        )


@dataclass
class User:
    """An X account."""

    id: Optional[str] = None
    screen_name: Optional[str] = None
    name: Optional[str] = None
    #: Canonical profile URL.
    url: Optional[str] = None
    description: str = ""
    location: Optional[str] = None
    website: Optional[str] = None
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    #: Join date, as X formats it.
    joined: Optional[str] = None
    verified: bool = False
    #: ``blue``, ``business``, ``government``, ``individual``, …
    verified_type: Optional[str] = None
    #: True when the account is protected (followers-only).
    protected: bool = False
    metrics: UserMetrics = field(default_factory=UserMetrics)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["User"]:
        if not isinstance(data, dict):
            return None
        return cls(
            id=data.get("id"),
            screen_name=data.get("screen_name"),
            name=data.get("name"),
            url=data.get("url"),
            description=_get(data, "description", ""),
            location=data.get("location"),
            website=data.get("website"),
            avatar_url=data.get("avatar_url"),
            banner_url=data.get("banner_url"),
            joined=data.get("joined"),
            verified=bool(data.get("verified", False)),
            verified_type=data.get("verified_type"),
            protected=bool(data.get("protected", False)),
            metrics=UserMetrics.from_dict(data.get("metrics")),
            raw=data,
        )


@dataclass
class MediaVariant:
    """One downloadable rendition of a video or gif; the list is best-first."""

    url: Optional[str] = None
    #: ``mp4`` is directly downloadable; ``m3u8`` is an HLS playlist.
    container: Optional[str] = None
    bitrate: Optional[int] = None
    codec: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaVariant":
        return cls(
            url=data.get("url"),
            container=data.get("container"),
            bitrate=data.get("bitrate"),
            codec=data.get("codec"),
        )


@dataclass
class MediaItem:
    """One attachment on a post."""

    id: Optional[str] = None
    #: ``photo``, ``video`` or ``gif``.
    type: Optional[str] = None
    #: Direct URL to the best rendition (originals for photos).
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    #: Video/gif duration in seconds.
    duration: Optional[float] = None
    #: Media type, e.g. ``image/jpeg`` or ``video/mp4``.
    format: Optional[str] = None
    #: Author-written alt text.
    alt_text: Optional[str] = None
    variants: List[MediaVariant] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["MediaItem"]:
        if not isinstance(data, dict):
            return None
        return cls(
            id=data.get("id"),
            type=data.get("type"),
            url=data.get("url"),
            thumbnail_url=data.get("thumbnail_url"),
            width=data.get("width"),
            height=data.get("height"),
            duration=data.get("duration"),
            format=data.get("format"),
            alt_text=data.get("alt_text"),
            variants=[MediaVariant.from_dict(v) for v in _get(data, "variants", [])],
            raw=data,
        )


@dataclass
class MediaListItem(MediaItem):
    """A media item from ``/v1/media``, with its position and a ready download link."""

    index: int = 0
    download_url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["MediaListItem"]:
        base = MediaItem.from_dict(data)
        if base is None:
            return None
        return cls(
            **{k: getattr(base, k) for k in base.__dataclass_fields__},
            index=_get(data, "index", 0),
            download_url=(data or {}).get("download_url"),
        )


@dataclass
class MediaList:
    """The ``/v1/media`` payload: every downloadable file attached to a post."""

    tweet_id: Optional[str] = None
    tweet_url: Optional[str] = None
    author: Optional[str] = None
    count: int = 0
    media: List[MediaListItem] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaList":
        items = [MediaListItem.from_dict(m) for m in _get(data, "media", [])]
        return cls(
            tweet_id=data.get("tweet_id"),
            tweet_url=data.get("tweet_url"),
            author=data.get("author"),
            count=_get(data, "count", 0),
            media=[item for item in items if item is not None],
            raw=data,
        )


@dataclass
class PollOption:
    label: Optional[str] = None
    votes: int = 0
    #: Share of the vote, rounded to one decimal.
    percent: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PollOption":
        return cls(
            label=data.get("label"),
            votes=_get(data, "votes", 0),
            percent=data.get("percent"),
        )


@dataclass
class Poll:
    total_votes: int = 0
    ends_at: Optional[str] = None
    options: List[PollOption] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Poll"]:
        if not isinstance(data, dict):
            return None
        return cls(
            total_votes=_get(data, "total_votes", 0),
            ends_at=data.get("ends_at"),
            options=[PollOption.from_dict(o) for o in _get(data, "options", [])],
        )


@dataclass
class Visibility:
    """What X shows readers about a post it has restricted."""

    #: X's notice on the post, in X's words.
    notice: Optional[str] = None
    notice_url: Optional[str] = None
    #: X labels the post as shown less widely.
    reach_limited: bool = False
    #: Actions X has turned off on this post, e.g. ``reply``, ``repost``.
    limited_actions: List[str] = field(default_factory=list)
    #: Country codes where the post is withheld.
    withheld_in: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Visibility"]:
        if not isinstance(data, dict):
            return None
        return cls(
            notice=data.get("notice"),
            notice_url=data.get("notice_url"),
            reach_limited=bool(data.get("reach_limited", False)),
            limited_actions=list(_get(data, "limited_actions", [])),
            withheld_in=data.get("withheld_in"),
        )


@dataclass
class EngagementMix:
    """Plain ratios between a post's public counts. No claim about ranking."""

    replies_per_like: Optional[float] = None
    quotes_per_like: Optional[float] = None
    reposts_per_like: Optional[float] = None
    likes_per_view: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "EngagementMix":
        data = data if isinstance(data, dict) else {}
        return cls(
            replies_per_like=data.get("replies_per_like"),
            quotes_per_like=data.get("quotes_per_like"),
            reposts_per_like=data.get("reposts_per_like"),
            likes_per_view=data.get("likes_per_view"),
        )


@dataclass
class Signals:
    """Facts about a post's reach from public data (``signals=True``).

    Not a ranking score and not a prediction.
    """

    age_seconds: Optional[int] = None
    #: Under 48 hours old, the window For You draws from.
    in_for_you_window: Optional[bool] = None
    #: ``possibly_eligible``, ``not_eligible`` or ``unknown``. Never more than
    #: "possibly": Home impressions are not public.
    new_author_slot: str = "unknown"
    engagement_mix: EngagementMix = field(default_factory=EngagementMix)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Signals"]:
        if not isinstance(data, dict):
            return None
        return cls(
            age_seconds=data.get("age_seconds"),
            in_for_you_window=data.get("in_for_you_window"),
            new_author_slot=data.get("new_author_slot") or "unknown",
            engagement_mix=EngagementMix.from_dict(data.get("engagement_mix")),
        )


@dataclass
class Entity:
    """A link, mention or hashtag with its character span in ``text``."""

    #: ``url``, ``mention`` or ``hashtag``.
    type: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    indices: Optional[List[int]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        return cls(
            type=data.get("type"),
            text=data.get("text"),
            url=data.get("url"),
            indices=data.get("indices"),
        )


@dataclass
class Tweet:
    """A post. Unknown values are ``None`` rather than absent."""

    id: Optional[str] = None
    url: Optional[str] = None
    text: str = ""
    #: Language code from X.
    lang: Optional[str] = None
    #: Creation date, as X formats it.
    created_at: Optional[str] = None
    #: Creation time as a Unix timestamp in seconds.
    created_timestamp: Optional[int] = None
    author: Optional[User] = None
    metrics: TweetMetrics = field(default_factory=TweetMetrics)
    media: List[MediaItem] = field(default_factory=list)
    poll: Optional[Poll] = None
    #: The quoted post, when this post quotes another.
    quote: Optional["Tweet"] = None
    #: Handle this post replies to.
    replying_to: Optional[str] = None
    #: URL of the post this replies to.
    replying_to_status: Optional[str] = None
    #: Community Note text, when one is attached.
    community_note: Optional[str] = None
    possibly_sensitive: bool = False
    #: What X shows readers about how this post may be seen; almost always None.
    visibility: Optional[Visibility] = None
    #: Present only when asked for with ``signals=True``.
    signals: Optional[Signals] = None
    #: True for long-form posts (formerly "note tweets").
    is_note_tweet: bool = False
    entities: List[Entity] = field(default_factory=list)
    #: Posting client, e.g. "Twitter for iPhone".
    client: Optional[str] = None
    provider: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Tweet"]:
        if not isinstance(data, dict):
            return None
        media = [MediaItem.from_dict(m) for m in _get(data, "media", [])]
        return cls(
            id=data.get("id"),
            url=data.get("url"),
            text=_get(data, "text", ""),
            lang=data.get("lang"),
            created_at=data.get("created_at"),
            created_timestamp=data.get("created_timestamp"),
            author=User.from_dict(data.get("author")),
            metrics=TweetMetrics.from_dict(data.get("metrics")),
            media=[item for item in media if item is not None],
            poll=Poll.from_dict(data.get("poll")),
            quote=cls.from_dict(data.get("quote")),
            replying_to=data.get("replying_to"),
            replying_to_status=data.get("replying_to_status"),
            community_note=data.get("community_note"),
            possibly_sensitive=bool(data.get("possibly_sensitive", False)),
            visibility=Visibility.from_dict(data.get("visibility")),
            signals=Signals.from_dict(data.get("signals")),
            is_note_tweet=bool(data.get("is_note_tweet", False)),
            entities=[Entity.from_dict(e) for e in _get(data, "entities", [])],
            client=data.get("client"),
            provider=data.get("provider"),
            raw=data,
        )


@dataclass
class Thread:
    """An unrolled thread: an ordered run of posts by one author."""

    root_id: Optional[str] = None
    author: Optional[User] = None
    count: int = 0
    #: True when the thread was longer than ``max_tweets``.
    truncated: bool = False
    tweets: List[Tweet] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Thread":
        tweets = [Tweet.from_dict(t) for t in _get(data, "tweets", [])]
        return cls(
            root_id=data.get("root_id"),
            author=User.from_dict(data.get("author")),
            count=_get(data, "count", 0),
            truncated=bool(data.get("truncated", False)),
            tweets=[t for t in tweets if t is not None],
            raw=data,
        )


@dataclass
class Timeline:
    """One page of an account's posts, newest first."""

    handle: Optional[str] = None
    count: int = 0
    #: Pass back as ``cursor`` for the next page; ``None`` when the timeline ends.
    next_cursor: Optional[str] = None
    tweets: List[Tweet] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Timeline":
        tweets = [Tweet.from_dict(t) for t in _get(data, "tweets", [])]
        return cls(
            handle=data.get("handle"),
            count=_get(data, "count", 0),
            next_cursor=data.get("next_cursor"),
            tweets=[t for t in tweets if t is not None],
            raw=data,
        )


@dataclass
class SearchResult:
    """One page of search results."""

    query: Optional[str] = None
    #: ``latest``, ``top``, ``photos`` or ``videos``.
    feed: str = "latest"
    since: Optional[str] = None
    until: Optional[str] = None
    count: int = 0
    #: Pass back as ``cursor`` for the next page; ``None`` on the last page.
    next_cursor: Optional[str] = None
    tweets: List[Tweet] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchResult":
        tweets = [Tweet.from_dict(t) for t in _get(data, "tweets", [])]
        return cls(
            query=data.get("query"),
            feed=_get(data, "feed", "latest"),
            since=data.get("since"),
            until=data.get("until"),
            count=_get(data, "count", 0),
            next_cursor=data.get("next_cursor"),
            tweets=[t for t in tweets if t is not None],
            raw=data,
        )


@dataclass
class Replies:
    """The direct replies to a post: the single page X serves, no paging."""

    tweet_id: Optional[str] = None
    tweet_url: Optional[str] = None
    #: ``top`` (most liked first) or ``recent`` (newest first).
    sort: str = "top"
    count: int = 0
    #: The post the replies are under.
    tweet: Optional[Tweet] = None
    replies: List[Tweet] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Replies":
        replies = [Tweet.from_dict(t) for t in _get(data, "replies", [])]
        return cls(
            tweet_id=data.get("tweet_id"),
            tweet_url=data.get("tweet_url"),
            sort=_get(data, "sort", "top"),
            count=_get(data, "count", 0),
            tweet=Tweet.from_dict(data.get("tweet")),
            replies=[t for t in replies if t is not None],
            raw=data,
        )


@dataclass
class UserList:
    """One page of an account's followers, or of the accounts it follows."""

    handle: Optional[str] = None
    #: ``followers`` or ``following``.
    relation: Optional[str] = None
    count: int = 0
    #: Pass back as ``cursor`` for the next page; ``None`` on the last page.
    next_cursor: Optional[str] = None
    users: List[User] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserList":
        users = [User.from_dict(u) for u in _get(data, "users", [])]
        return cls(
            handle=data.get("handle"),
            relation=data.get("relation"),
            count=_get(data, "count", 0),
            next_cursor=data.get("next_cursor"),
            users=[u for u in users if u is not None],
            raw=data,
        )


@dataclass
class AccountHistory:
    """An account's posts in bulk, newest first."""

    handle: Optional[str] = None
    count: int = 0
    include_replies: bool = False
    include_reposts: bool = False
    since: Optional[str] = None
    until: Optional[str] = None
    #: True when the walk stopped before the timeline or window ran out.
    truncated: bool = False
    #: ``max_posts``, ``window``, ``end_of_timeline``, ``page_limit`` or ``upstream_error``.
    stop_reason: Optional[str] = None
    newest: Optional[str] = None
    oldest: Optional[str] = None
    tweets: List[Tweet] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountHistory":
        tweets = [Tweet.from_dict(t) for t in _get(data, "tweets", [])]
        return cls(
            handle=data.get("handle"),
            count=_get(data, "count", 0),
            include_replies=bool(data.get("include_replies", False)),
            include_reposts=bool(data.get("include_reposts", False)),
            stop_reason=data.get("stop_reason"),
            since=data.get("since"),
            until=data.get("until"),
            truncated=bool(data.get("truncated", False)),
            newest=data.get("newest"),
            oldest=data.get("oldest"),
            tweets=[t for t in tweets if t is not None],
            raw=data,
        )


@dataclass
class Trend:
    rank: int = 0
    name: Optional[str] = None
    #: Label X attaches, e.g. "Politics · Trending".
    context: Optional[str] = None
    posts: Optional[int] = None
    url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trend":
        return cls(
            rank=_get(data, "rank", 0),
            name=data.get("name"),
            context=data.get("context"),
            posts=data.get("posts"),
            url=data.get("url"),
        )


@dataclass
class TrendsResult:
    count: int = 0
    trends: List[Trend] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrendsResult":
        return cls(
            count=_get(data, "count", 0),
            trends=[Trend.from_dict(t) for t in _get(data, "trends", [])],
            raw=data,
        )


@dataclass
class BulkItem:
    """One entry in a bulk response. Failures are per item, not per request."""

    ok: bool = False
    #: The URL or id as supplied by the caller.
    input: Optional[str] = None
    tweet: Optional[Tweet] = None
    #: ``{"status": int, "message": str}`` when ``ok`` is False.
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BulkItem":
        return cls(
            ok=bool(data.get("ok", False)),
            input=data.get("input"),
            tweet=Tweet.from_dict(data.get("tweet")),
            error=data.get("error"),
        )


@dataclass
class BulkResult:
    requested: int = 0
    succeeded: int = 0
    failed: int = 0
    results: List[BulkItem] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BulkResult":
        return cls(
            requested=_get(data, "requested", 0),
            succeeded=_get(data, "succeeded", 0),
            failed=_get(data, "failed", 0),
            results=[BulkItem.from_dict(r) for r in _get(data, "results", [])],
            raw=data,
        )


@dataclass
class RateLimit:
    """Rate-limit state read from the last response's headers."""

    #: Requests allowed in the window for that endpoint.
    limit: Optional[int] = None
    #: Requests left in the current window.
    remaining: Optional[int] = None
    #: Raw ``x-ratelimit-reset`` value (Unix seconds).
    reset: Optional[int] = None
    #: ``reset`` as an aware datetime, in UTC.
    reset_at: Optional[Any] = None


@dataclass
class ResponseMeta:
    """What the last response said about itself, read from its headers.

    Which upstream answered is deliberately not among it: the API stopped
    publishing that, because it describes how the service is built rather than
    anything about the post.
    """

    format: str = "json"
    #: ``x-xcrap-cache``: hit, miss or bypass.
    cache: Optional[str] = None
    #: ``x-markdown-tokens``: estimated tokens, markdown responses only.
    markdown_tokens: Optional[int] = None


@dataclass
class DownloadedMedia:
    """One media file streamed through XCrap."""

    #: Suggested filename from ``content-disposition``.
    filename: str
    content_type: str
    content_length: Optional[int]
    #: The file itself.
    content: bytes

    def save(self, path: Optional[str] = None) -> str:
        """Write the bytes to ``path`` (default: the suggested filename).

        Returns:
            The path written to.
        """
        target = path or self.filename
        with open(target, "wb") as handle:
            handle.write(self.content)
        return target
