"""
Sends an email via the Gmail API, using the same token.pickle created by
gmail_auth.py (now scoped for both reading and sending).
"""
import os
import pickle
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build

TOKEN_PATH = os.environ.get("TOKEN_PATH", "token.pickle")


def _get_service():
    with open(TOKEN_PATH, "rb") as f:
        creds = pickle.load(f)
    return build("gmail", "v1", credentials=creds)


def send_email(to: str, subject: str, body_html: str) -> None:
    """
    Sends an HTML email to the given address, from whichever account
    token.pickle is authorized for.
    """
    service = _get_service()

    message = MIMEText(body_html, "html")
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()


if __name__ == "__main__":
    # quick manual test
    send_email(
        to="REPLACE_WITH_RECIPIENT@example.com",
        subject="Crypto bot test email",
        body_html="<p>If you're reading this, sending works.</p>",
    )
    print("Sent.")
