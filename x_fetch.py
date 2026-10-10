"""
Fetches recent posts from specific X accounts, for the past N days.
Reusable by both the weekly (BTC/ETH) and monthly (obscure token) jobs —
just pass in whichever list of usernames matters for that run.
"""
import os
import time
from datetime import datetime, timedelta, UTC
import requests

BEARER_TOKEN = os.environ["X_BEARER_TOKEN"].strip()
BASE_URL = "https://api.twitter.com/2"

HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}

# Running tally of what X returned to us during this process. X's pay-per-use
# billing is per resource returned (posts and user objects), so counting what
# comes back is how the digest email estimates its X API cost. One process =
# one job run, so a module-level tally is enough.
_READ_STATS = {"posts": 0, "users": 0, "by_account": {}}


def get_read_stats() -> dict:
    """Returns {posts, users, by_account: {username: posts}} tallied so far."""
    return {
        "posts": _READ_STATS["posts"],
        "users": _READ_STATS["users"],
        "by_account": dict(_READ_STATS["by_account"]),
    }


def _get_user_id(username: str) -> str | None:
    resp = requests.get(
        f"{BASE_URL}/users/by/username/{username}",
        headers=HEADERS,
    )
    if resp.status_code != 200:
        print(f"  Could not look up @{username}: {resp.status_code} {resp.text}")
        return None
    _READ_STATS["users"] += 1  # a user object was returned (billed separately from posts)
    return resp.json()["data"]["id"]


def _get_user_posts(user_id: str, lookback_days: int) -> list[dict]:
    start_time = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    resp = requests.get(
        f"{BASE_URL}/users/{user_id}/tweets",
        headers=HEADERS,
        params={
            "max_results": 100,
            "start_time": start_time,
            "exclude": "retweets,replies",
            "tweet.fields": "created_at,note_tweet",
        },
    )

    if resp.status_code == 429:
        # rate limited — wait and retry once
        reset = int(resp.headers.get("x-rate-limit-reset", time.time() + 60))
        wait = max(reset - int(time.time()), 1)
        print(f"  Rate limited, waiting {wait}s...")
        time.sleep(wait)
        resp = requests.get(
            f"{BASE_URL}/users/{user_id}/tweets",
            headers=HEADERS,
            params={
                "max_results": 100,
                "start_time": start_time,
                "exclude": "retweets,replies",
                "tweet.fields": "created_at,note_tweet",
            },
        )

    if resp.status_code != 200:
        print(f"  Error fetching posts: {resp.status_code} {resp.text}")
        return []

    return resp.json().get("data", [])


def _build_search_query(username: str, phrases: list[str]) -> str:
    query = f"from:{username} -is:retweet -is:reply"
    # quoted phrases match the exact phrase; OR'd together so a post matching
    # ANY of them is returned
    phrase_clause = " OR ".join(f'"{p}"' for p in phrases)
    return f"{query} ({phrase_clause})"


def _search_recent_posts(username: str, lookback_days: int, phrases: list[str]) -> list[dict]:
    """
    Uses the /tweets/search/recent endpoint (last 7 days only) with a
    `from:username (\"phrase1\" OR \"phrase2\")` query, so filtering happens
    server-side -- we only pay for and receive posts that actually match,
    instead of fetching the whole timeline and filtering locally. Also skips
    the separate user-id lookup, since `from:username` works directly.
    """
    start_time = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    query = _build_search_query(username, phrases)
    params = {
        "query": query,
        "start_time": start_time,
        "max_results": 100,
        "tweet.fields": "created_at,note_tweet",
    }

    resp = requests.get(f"{BASE_URL}/tweets/search/recent", headers=HEADERS, params=params)

    if resp.status_code == 429:
        reset = int(resp.headers.get("x-rate-limit-reset", time.time() + 60))
        wait = max(reset - int(time.time()), 1)
        print(f"  Rate limited, waiting {wait}s...")
        time.sleep(wait)
        resp = requests.get(f"{BASE_URL}/tweets/search/recent", headers=HEADERS, params=params)

    if resp.status_code != 200:
        print(f"  Error searching posts: {resp.status_code} {resp.text}")
        return []

    return resp.json().get("data", [])


def fetch_x_posts(
    username: str, lookback_days: int = 7, phrases: list[str] | None = None
) -> list[dict]:
    """
    Returns a list of {username, text, date, id} dicts for one account's posts
    within the lookback window, in chronological (oldest-first) order.

    If `phrases` is given (non-empty), only posts containing at least one of
    the phrases are returned -- used to pull out e.g. a daily "today's
    biggest market events" post from an account that also posts a lot of
    unrelated engagement content. This is done server-side via the X search
    endpoint (query `from:username ("phrase1" OR "phrase2")`), which only
    covers the last 7 days -- fine here since that's already our lookback
    window for the weekly job. An empty or omitted list falls back to the
    regular unfiltered timeline fetch.
    """
    print(f"Fetching @{username}...")

    if phrases:
        posts = _search_recent_posts(username, lookback_days, phrases)
    else:
        user_id = _get_user_id(username)
        if not user_id:
            return []
        posts = _get_user_posts(user_id, lookback_days)

    # every post X returned here is billed, whether or not it ends up cited
    _READ_STATS["posts"] += len(posts)
    by_account = _READ_STATS["by_account"]
    by_account[username] = by_account.get(username, 0) + len(posts)

    # X returns posts newest-first; reverse to oldest-first so threads read
    # in logical order and later posts can correctly reference earlier ones
    result = []
    for post in reversed(posts):
        # long-form "Note Tweets" (the ones with a "Show more" button in the
        # UI) get truncated in the default text field -- the full text only
        # shows up in note_tweet.text when present
        full_text = post.get("note_tweet", {}).get("text") or post["text"]
        result.append({
            "username": username,
            "text": full_text,
            "date": post.get("created_at", ""),
            "id": post["id"],
        })

    if phrases:
        print(f"  {len(result)} posts matched phrase filter (server-side)")

    return result


if __name__ == "__main__":
    # quick manual test -- unfiltered
#    posts = fetch_x_posts("danheld", lookback_days=7)
#    print(f"\nFound {len(posts)} posts")
#    for p in posts:
#        print(f"- @{p['username']} ({p['date']}): {p['text']}...")

    # quick manual test -- phrase-filtered (edit username/phrase to try it)
    filtered = fetch_x_posts("VirtualBacon", lookback_days=7, phrases=["most important market events over the last 24 hours"])
    print(f"\nFound {len(filtered)} phrase-matched posts:")
    for p in filtered:
        print(f"- @{p['username']} ({p['date']}): {p['text']}...")
