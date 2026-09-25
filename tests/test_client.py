"""Smoke tests for the xcrap SDK against a live XCrap server.

    pytest -v

These are integration tests on purpose: the point of an SDK smoke test is to
prove the client and a real deployment still agree about the contract. A few
offline tests (URL building, format validation, retry policy) use a stub
transport so they run without a server.
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx
import pytest

from xcrap import (
    DEFAULT_BASE_URL,
    VERSION,
    AccountHistory,
    AsyncXcrap,
    BulkResult,
    MediaList,
    Replies,
    SearchResult,
    Thread,
    Timeline,
    TrendsResult,
    Tweet,
    User,
    UserList,
    Xcrap,
    XcrapBadRequest,
    XcrapConnectionError,
    XcrapNotFound,
)

BASE_URL = os.environ.get("XCRAP_BASE_URL", DEFAULT_BASE_URL)
TWEET = os.environ.get("XCRAP_TEST_TWEET", "https://x.com/jack/status/20")
HANDLE = os.environ.get("XCRAP_TEST_HANDLE", "jack")
DEAD_TWEET = "https://x.com/jack/status/1111111111111111111"


@pytest.fixture(scope="module")
def client():
    with Xcrap(BASE_URL, timeout=45.0) as instance:
        yield instance


# ── offline ───────────────────────────────────────────────────────────────


def test_defaults_and_base_url_override():
    assert Xcrap().base_url == "https://xcrap.cc"
    assert Xcrap("https://proxy.example.org/").base_url == "https://proxy.example.org"
    assert f"xcrap-python-sdk/{VERSION}" in Xcrap().user_agent


def test_build_url_drops_empty_values():
    url = Xcrap(BASE_URL).build_url("/v1/tweet", {"url": TWEET, "cursor": None, "count": ""})
    assert url.startswith(f"{BASE_URL}/v1/tweet?url=")
    assert "cursor" not in url and "count" not in url


def test_unknown_format_is_rejected_before_the_network():
    with pytest.raises(XcrapBadRequest) as info:
        Xcrap(BASE_URL).tweet(TWEET, format="xml")
    assert "Use one of" in str(info.value)


def test_bulk_limits_are_enforced_client_side():
    xcrap = Xcrap(BASE_URL)
    with pytest.raises(XcrapBadRequest):
        xcrap.bulk([])
    with pytest.raises(XcrapBadRequest) as info:
        xcrap.bulk([TWEET] * 51)
    assert "at most 50" in str(info.value)


def test_503_is_retried_once_and_404_never_is():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        first_status_call = len(calls) == 1 and request.url.path == "/v1/user"
        status = 503 if first_status_call else 404
        return httpx.Response(status, json={"error": {"status": status, "code": "x", "message": "stub"}})

    transport = httpx.MockTransport(handler)
    xcrap = Xcrap(
        "http://stub.invalid",
        retries=1,
        retry_delay=0.01,
        client=httpx.Client(transport=transport),
    )

    with pytest.raises(XcrapNotFound):
        xcrap.user("naval")
    assert len(calls) == 2, "503 should be retried exactly once"

    calls.clear()
    with pytest.raises(XcrapNotFound):
        xcrap.tweet(TWEET)
    assert len(calls) == 1, "a 4xx must never be retried"


def _recording_client(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, json={"query": "q", "feed": "top", "tweets": [], "users": [], "replies": []})

    return Xcrap("http://stub.invalid", retries=0, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_new_endpoints_build_the_right_requests_and_models():
    calls = []
    xcrap = _recording_client(calls)

    page = xcrap.search("from:nasa mars", feed="top", since=datetime(2026, 1, 1), cursor="c1")
    assert isinstance(page, SearchResult)
    assert isinstance(xcrap.replies("https://x.com/jack/status/20", sort="recent"), Replies)
    assert isinstance(xcrap.followers("jack", cursor="f1"), UserList)
    assert isinstance(xcrap.following("@jack"), UserList)
    assert isinstance(xcrap.user_history("jack", max_posts=50, include_replies=True), AccountHistory)

    assert [url.path for url in calls] == [
        "/v1/search",
        "/v1/replies",
        "/v1/user/followers",
        "/v1/user/following",
        "/v1/user/history",
    ]
    search = calls[0].params
    assert search["q"] == "from:nasa mars"
    assert search["feed"] == "top"
    assert search["since"].startswith("2026-01-01")
    assert search["cursor"] == "c1"
    assert calls[1].params["sort"] == "recent"
    assert calls[4].params["max_posts"] == "50"
    assert calls[4].params["include_replies"] == "true"


def test_unreachable_host_raises_xcrap_connection_error():
    xcrap = Xcrap("http://127.0.0.1:1", timeout=2.0, retries=0)
    with pytest.raises(XcrapConnectionError) as info:
        xcrap.tweet(TWEET)
    assert "Could not reach" in str(info.value)


# ── live: sync ────────────────────────────────────────────────────────────


def test_rate_limit_headers_are_exposed(client):
    client.tweet(TWEET)
    assert client.rate_limit is not None
    assert isinstance(client.rate_limit.limit, int)
    assert isinstance(client.rate_limit.remaining, int)
    assert isinstance(client.rate_limit.reset_at, datetime)
    print(
        f"  rate limit {client.rate_limit.remaining}/{client.rate_limit.limit},"
        f" resets {client.rate_limit.reset_at.isoformat()}"
    )


def test_tweet_returns_the_canonical_shape(client):
    tweet = client.tweet(TWEET)
    assert isinstance(tweet, Tweet)
    assert tweet.id and isinstance(tweet.text, str)
    assert tweet.author is not None and tweet.author.screen_name
    assert tweet.metrics.likes is None or isinstance(tweet.metrics.likes, int)
    assert isinstance(tweet.media, list)
    print(f"  tweet {tweet.id} by @{tweet.author.screen_name}: {tweet.text[:40]!r}")
    print(f"  cache={client.last_meta.cache}")


def test_markdown_option_returns_markdown_and_token_estimate(client):
    markdown = client.tweet(TWEET, markdown=True)
    assert isinstance(markdown, str) and markdown
    assert client.last_meta.format == "markdown"
    assert client.last_meta.markdown_tokens and client.last_meta.markdown_tokens > 0
    print(f"  markdown {len(markdown)} chars, ~{client.last_meta.markdown_tokens} tokens")


def test_yaml_format_returns_a_string(client):
    text = client.tweet(TWEET, format="yaml")
    assert isinstance(text, str)
    assert text.lstrip().startswith("id:")


def test_user_returns_a_profile(client):
    user = client.user(HANDLE)
    assert isinstance(user, User)
    assert user.screen_name.lower() == HANDLE.lower()
    assert user.url == f"https://x.com/{user.screen_name}"
    assert isinstance(user.metrics.followers, int)
    print(f"  @{user.screen_name}: {user.metrics.followers:,} followers")


def test_user_tweets_pages_with_a_cursor(client):
    page = client.user_tweets(HANDLE, count=5)
    assert isinstance(page, Timeline)
    assert page.handle.lower() == HANDLE.lower()
    assert len(page.tweets) <= 5
    assert page.next_cursor is None or isinstance(page.next_cursor, str)
    print(f"  timeline {page.count} posts, next_cursor {'present' if page.next_cursor else 'null'}")


def test_iter_user_tweets_yields_posts(client):
    seen = [post.id for post in client.iter_user_tweets(HANDLE, count=5, limit=3)]
    assert len(seen) <= 3
    assert all(isinstance(identifier, str) for identifier in seen)
    print(f"  iterated {len(seen)} posts")


def test_thread_unrolls(client):
    thread = client.thread(TWEET, max_tweets=5)
    assert isinstance(thread, Thread)
    assert thread.count == len(thread.tweets)
    assert isinstance(thread.truncated, bool)
    print(f"  thread {thread.root_id}: {thread.count} posts, truncated={thread.truncated}")


def test_trends_returns_a_ranked_list(client):
    trends = client.trends(count=5)
    assert isinstance(trends, TrendsResult)
    assert trends.count == len(trends.trends)
    print(f"  trends: {trends.count} returned")


def test_media_lists_attachments(client):
    try:
        listing = client.media(TWEET)
    except XcrapNotFound:
        print("  media: this post has none (404 as expected)")
        return
    assert isinstance(listing, MediaList)
    for item in listing.media:
        assert "/v1/media/download" in item.download_url
    print(f"  media: {listing.count} item(s)")


def test_bulk_reports_per_item_failures(client):
    result = client.bulk([TWEET, DEAD_TWEET])
    assert isinstance(result, BulkResult)
    assert result.requested == 2
    assert result.succeeded + result.failed == 2
    for item in result.results:
        assert item.input
        assert (item.tweet is not None) == item.ok
    print(f"  bulk: {result.succeeded} ok, {result.failed} failed")


def test_missing_parameter_raises_bad_request_with_advice(client):
    with pytest.raises(XcrapBadRequest) as info:
        client.tweet("")
    error = info.value
    assert error.status == 400
    assert error.code == "bad_request"
    assert "Check the parameter" in error.message
    print(f"  400 -> {error.message[:90]}…")


def test_dead_post_raises_not_found_with_advice(client):
    with pytest.raises(XcrapNotFound) as info:
        client.tweet(DEAD_TWEET)
    error = info.value
    assert error.status == 404
    assert "retrying will not help" in error.message
    # Why, when X says; ``unavailable`` when it does not.
    assert error.reason in {
        "post_deleted", "author_protected", "author_suspended",
        "withheld", "removed_by_x", "age_restricted", "unavailable",
    }
    print(f"  404 -> {error.message[:90]}…")


def test_search_returns_a_page_or_says_capacity_is_spent(client):
    try:
        page = client.search("from:nasa", feed="latest")
    except Exception as error:  # noqa: BLE001 - only a 503 is acceptable here
        assert getattr(error, "status", None) == 503, f"search failed: {error}"
        print("  search: 503, capacity spent or not configured on this deployment")
        return
    assert isinstance(page, SearchResult)
    assert page.count == len(page.tweets)
    assert page.next_cursor is None or isinstance(page.next_cursor, str)
    print(f"  search: {page.count} posts, next_cursor {'present' if page.next_cursor else 'null'}")


def test_fresh_bypasses_the_cache(client):
    client.tweet(TWEET, fresh=True)
    assert client.last_meta.cache in {"bypass", "miss"}
    print(f"  fresh=True -> cache={client.last_meta.cache}")


# ── live: async ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_client_matches_the_sync_one():
    async with AsyncXcrap(BASE_URL, timeout=45.0) as xcrap:
        tweet = await xcrap.tweet(TWEET)
        assert isinstance(tweet, Tweet)
        assert tweet.author.screen_name

        markdown = await xcrap.tweet(TWEET, markdown=True)
        assert isinstance(markdown, str)
        assert xcrap.last_meta.markdown_tokens > 0

        assert xcrap.rate_limit is not None
        print(
            f"  async: tweet {tweet.id}, ~{xcrap.last_meta.markdown_tokens} md tokens,"
            f" {xcrap.rate_limit.remaining}/{xcrap.rate_limit.limit} calls left"
        )


@pytest.mark.asyncio
async def test_async_iterator_and_errors():
    async with AsyncXcrap(BASE_URL, timeout=45.0) as xcrap:
        seen = []
        async for post in xcrap.iter_user_tweets(HANDLE, count=5, limit=3):
            seen.append(post.id)
        assert len(seen) <= 3

        with pytest.raises(XcrapNotFound):
            await xcrap.tweet(DEAD_TWEET)
        print(f"  async: iterated {len(seen)} posts, 404 raised as XcrapNotFound")
