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


def _get_user_id(username: str) -> str | None:
    resp = requests.get(
        f"{BASE_URL}/users/by/username/{username}",
        headers=HEADERS,
    )
    if resp.status_code != 200:
        print(f"  Could not look up @{username}: {resp.status_code} {resp.text}")
        return None
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
            "tweet.fields": "created_at",
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
                "tweet.fields": "created_at",
            },
        )

    if resp.status_code != 200:
        print(f"  Error fetching posts: {resp.status_code} {resp.text}")
        return []

    return resp.json().get("data", [])


def fetch_x_posts(username: str, lookback_days: int = 7) -> list[dict]:
    """
    Returns a list of {username, text, date} dicts for one account's posts
    within the lookback window, in chronological (oldest-first) order.
    """
    print(f"Fetching @{username}...")
    user_id = _get_user_id(username)
    if not user_id:
        return []

    posts = _get_user_posts(user_id, lookback_days)
    # X returns posts newest-first; reverse to oldest-first so threads read
    # in logical order and later posts can correctly reference earlier ones
    return [
        {
            "username": username,
            "text": post["text"],
            "date": post.get("created_at", ""),
        }
        for post in reversed(posts)
    ]


if __name__ == "__main__":
    # quick manual test
    posts = fetch_x_posts("VitalikButerin", lookback_days=7)
    print(f"\nFound {len(posts)} posts")
    for p in posts:
        print(f"- @{p['username']} ({p['date']}): {p['text'][:80]}...")
