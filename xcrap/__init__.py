"""xcrap — the official Python client for XCrap (https://xcrap.cc).

XCrap turns an X/Twitter URL into structured data, or into markdown ready for a
language model. No API key, no OAuth, no signup.

    from xcrap import Xcrap

    with Xcrap() as xcrap:
        tweet = xcrap.tweet("https://x.com/jack/status/20")
        print(tweet.text)
        print(f"{xcrap.rate_limit.remaining}/{xcrap.rate_limit.limit} calls left")

Full reference: https://xcrap.cc/sdk/python
"""

from .client import (
    DEFAULT_BASE_URL,
    FORMATS,
    VERSION,
    AsyncXcrap,
    Xcrap,
)
from .errors import (
    XcrapBadRequest,
    XcrapConnectionError,
    XcrapError,
    XcrapNotFound,
    XcrapOptedOut,
    XcrapRateLimited,
    XcrapUpstreamError,
)
from .models import (
    AccountHistory,
    BulkItem,
    BulkResult,
    DownloadedMedia,
    Entity,
    MediaItem,
    MediaList,
    MediaListItem,
    MediaVariant,
    Poll,
    Visibility,
    Signals,
    EngagementMix,
    PollOption,
    RateLimit,
    Replies,
    ResponseMeta,
    SearchResult,
    Thread,
    Timeline,
    Trend,
    TrendsResult,
    Tweet,
    TweetMetrics,
    User,
    UserList,
    UserMetrics,
)

__version__ = VERSION

__all__ = [
    # clients
    "Xcrap",
    "AsyncXcrap",
    "VERSION",
    "__version__",
    "DEFAULT_BASE_URL",
    "FORMATS",
    # errors
    "XcrapError",
    "XcrapBadRequest",
    "XcrapNotFound",
    "XcrapRateLimited",
    "XcrapOptedOut",
    "XcrapUpstreamError",
    "XcrapConnectionError",
    # models
    "Tweet",
    "TweetMetrics",
    "User",
    "UserMetrics",
    "MediaItem",
    "MediaListItem",
    "MediaList",
    "MediaVariant",
    "Poll",
    "Visibility",
    "Signals",
    "EngagementMix",
    "PollOption",
    "Entity",
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
