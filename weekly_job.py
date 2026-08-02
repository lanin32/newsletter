"""
The weekly job: fetches newsletters + X posts, summarizes them into three
sections, builds a simple HTML email, and sends it.

Usage:
    python weekly_job.py
"""
from datetime import date
import time
import yaml

from gmail_fetch import fetch_newsletter_emails, fetch_latest_email
from x_fetch import fetch_x_posts
from weekly_summarize import summarize_weekly_digest
from gmail_send import send_email
from citations import linkify_citations


def build_sources(config: dict) -> dict:
    sources = {}

    for nl in config.get("newsletters", []):
        if "REPLACE_ME" in nl["gmail_query"]:
            print(f"Skipping {nl['name']} — gmail_query not configured yet")
            continue
        print(f"Fetching {nl['name']}...")
        emails = fetch_newsletter_emails(nl["gmail_query"], lookback_days=nl["lookback_days"])
        sources[f"{nl['name']} (newsletter)"] = emails
        print(f"  found {len(emails)} emails")

    for token, accounts in config.get("x_accounts", {}).items():
        for account in accounts:
            posts = fetch_x_posts(account, lookback_days=7)
            sources[f"{account} (X posts)"] = posts
            print(f"  found {len(posts)} posts")
            time.sleep(1)  # small buffer between accounts to be polite to rate limits

    return sources


def build_sources_footer_html(items_meta: list[dict]) -> str:
    """
    Lists every source item, grouped by source, with its citation number and
    link when it has one (matching the inline [N] citations exactly) -- or
    just the title when it doesn't (e.g. a newsletter with no link found).
    """
    if not items_meta:
        return "<span style=\"color: #999999; font-size: 12px; font-family: sans-serif;\">No sources found this week.</span>"

    grouped: dict[str, list[dict]] = {}
    for m in items_meta:
        grouped.setdefault(m["source_name"], []).append(m)

    group_blocks = []
    for source_name, items in grouped.items():
        entries = []
        for m in items:
            if m["citation_num"] is not None:
                entries.append(
                    f'<li><a href="{m["url"]}" style="color: #888888; text-decoration: none;">'
                    f'[{m["citation_num"]}]</a> {m["label"]}</li>'
                )
            else:
                entries.append(f"<li>{m['label']}</li>")
        group_blocks.append(
            f'<div style="margin-bottom: 10px;">'
            f'<strong style="color: #777777;">{source_name}</strong>'
            f'<ul style="margin: 4px 0 0; padding-left: 18px;">{"".join(entries)}</ul>'
            f"</div>"
        )

    return f"""
    <span style="color: #999999; font-size: 12px; font-family: sans-serif;">SOURCES THIS WEEK</span>
    <div style="color: #999999; font-size: 12px; font-family: sans-serif; margin-top: 8px;">
      {''.join(group_blocks)}
    </div>
    """


def build_email_html(digest: dict[str, str], items_meta: list[dict]) -> str:
    citation_map = {
        m["citation_num"]: m["url"] for m in items_meta if m["citation_num"] is not None
    }

    def paragraph(text: str) -> str:
        linked = linkify_citations(text, citation_map)
        return "".join(
            f'<p style="margin: 0 0 12px 0; color: #333333; font-size: 14px; line-height: 1.6;">{chunk.strip()}</p>'
            for chunk in linked.split("\n\n") if chunk.strip()
        )

    def section(title: str, accent_color: str, content: str) -> str:
        return f"""
        <tr>
          <td style="padding: 24px 32px; border-left: 4px solid {accent_color};">
            <h2 style="margin: 0 0 12px 0; font-size: 17px; color: #111111; font-family: sans-serif;">
              {title}
            </h2>
            {content}
          </td>
        </tr>
        <tr><td style="height: 8px;"></td></tr>
        """

    today_str = date.today().strftime("%B %d, %Y")

    return f"""
    <html>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta charset="utf-8">
      </head>
      <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: sans-serif;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 24px 0;">
          <tr>
            <td align="center">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                     style="background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e0e0e0; max-width: 600px;">
                <tr>
                  <td style="background-color: #111111; padding: 20px 32px;">
                    <span style="color: #ffffff; font-size: 20px; font-weight: bold; font-family: sans-serif;">
                      Crypto Weekly
                    </span>
                    <br>
                    <span style="color: #aaaaaa; font-size: 13px; font-family: sans-serif;">
                      {today_str}
                    </span>
                  </td>
                </tr>
                <tr><td style="height: 8px;"></td></tr>

                {section("Bitcoin", "#f7931a", paragraph(digest['btc']))}
                {section("Ethereum", "#627eea", paragraph(digest['eth']))}
                {section("General Market", "#888888", paragraph(digest['general']))}

                <tr>
                  <td style="padding: 16px 32px; background-color: #fafafa; border-top: 1px solid #eeeeee;">
                    {build_sources_footer_html(items_meta)}
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


def main():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    email_cfg = config["email"]

    print("Checking for last week's digest (for continuity)...")
    previous = fetch_latest_email(f'subject:"{email_cfg["subject"]}"')
    previous_digest = previous["body"] if previous else None
    if previous:
        print(f"  found one from {previous['date']}")
    else:
        print("  none found (first run?)")

    sources = build_sources(config)

    print("\nSummarizing...")
    digest, items_meta = summarize_weekly_digest(sources, previous_digest=previous_digest)

    print("\nBuilding email...")
    html = build_email_html(digest, items_meta)

    subject = f"{email_cfg['subject']} — {date.today().strftime('%b %d, %Y')}"

    print(f"Sending to {email_cfg['to']}...")
    send_email(
        to=email_cfg["to"],
        subject=subject,
        body_html=html,
        bcc=email_cfg.get("read_account"),
    )
    print("Done.")


if __name__ == "__main__":
    main()
