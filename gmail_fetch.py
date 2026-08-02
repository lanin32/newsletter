"""
Fetches emails matching a Gmail search query from the last N days and
returns their plain-text bodies.
"""
import os
import re
import pickle
import base64
from datetime import datetime, timedelta, UTC
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

TOKEN_PATH = os.environ.get("TOKEN_PATH", "token.pickle")

# Matches the common "view this online" footer pattern used by most email
# newsletter platforms (beehiiv, Substack, etc.) -- a trigger phrase followed
# shortly by the actual public URL to the web version of the post.
_VIEW_ONLINE_PATTERN = re.compile(
    r"(?:view (?:the )?post online|view this post on the web|"
    r"view in (?:your )?browser|read (?:it )?online)"
    r"[^\n]*\n*\s*(https?://\S+)",
    re.IGNORECASE,
)


def _extract_view_online_link(body: str) -> str | None:
    match = _VIEW_ONLINE_PATTERN.search(body)
    return match.group(1) if match else None


def _get_service():
    with open(TOKEN_PATH, "rb") as f:
        creds = pickle.load(f)
    return build("gmail", "v1", credentials=creds)


def _extract_body(payload) -> str:
    """Walk the MIME tree and pull out readable text (prefer plain, fall back to HTML)."""
    def find_part(parts, mime_type):
        for part in parts:
            if part.get("mimeType") == mime_type:
                return part
            if "parts" in part:
                found = find_part(part["parts"], mime_type)
                if found:
                    return found
        return None

    parts = payload.get("parts", [payload])

    plain = find_part(parts, "text/plain")
    if plain and "data" in plain.get("body", {}):
        data = plain["body"]["data"]
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    html_part = find_part(parts, "text/html")
    if html_part and "data" in html_part.get("body", {}):
        data = html_part["body"]["data"]
        html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)

    return ""


def _get_email(service, msg_id: str) -> dict:
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    body = _extract_body(msg["payload"])

    return {
        "subject": headers.get("Subject", "(no subject)"),
        "date": headers.get("Date", ""),
        "body": body,
        "url": _extract_view_online_link(body),
    }


def fetch_newsletter_emails(gmail_query: str, lookback_days: int = 7) -> list[dict]:
    """
    Returns a list of {subject, date, body} dicts for emails matching the
    query within the lookback window.
    """
    service = _get_service()

    after_date = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    full_query = f"{gmail_query} after:{after_date}"

    results = service.users().messages().list(userId="me", q=full_query).execute()
    messages = results.get("messages", [])

    return [_get_email(service, m["id"]) for m in messages]


def fetch_latest_email(gmail_query: str) -> dict | None:
    """
    Returns the single most recent email matching the query, with no date
    window -- used to pull up "the previous digest," whenever it was sent.
    Returns None if nothing matches (e.g. first run, nothing sent yet).
    """
    service = _get_service()

    results = service.users().messages().list(
        userId="me", q=gmail_query, maxResults=1
    ).execute()
    messages = results.get("messages", [])

    if not messages:
        return None

    return _get_email(service, messages[0]["id"])


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    newsletter_cfg = config["newsletters"][0]
    print(f"Query: {newsletter_cfg['gmail_query']}, lookback: {newsletter_cfg['lookback_days']} days")

    emails = fetch_newsletter_emails(
        newsletter_cfg["gmail_query"],
        lookback_days=newsletter_cfg["lookback_days"],
    )
    print(f"Found {len(emails)} emails")
    for e in emails:
        url_note = e["url"] if e["url"] else "(no link found)"
        print(f"- {e['subject']} ({e['date']}) — {len(e['body'])} chars — {url_note}")
