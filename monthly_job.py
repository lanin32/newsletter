"""
The monthly job: for each configured small-cap token, fetches its X accounts'
posts over the past month, summarizes each token independently (no pooling --
see monthly_summarize.py for why), builds one email with a section per token,
and sends it.

Usage:
    python monthly_job.py
"""
from datetime import date
import os
import time
import yaml

from x_fetch import fetch_x_posts, get_read_stats
from monthly_summarize import summarize_token_digest
from gmail_fetch import fetch_latest_email
from gmail_send import send_email
from citations import linkify_citations
from email_render import render_cards, render_section, render_cost_footer, COST_FOOTER_TITLE
from usage_cost import estimate_x_cost


def parse_previous_digest(text: str, symbols: list[str]) -> dict[str, str]:
    """
    Splits last month's plain-text digest back into per-token sections.
    Relies on the email's own structure: each token's symbol renders as its
    own line (from the <h2>{symbol}</h2> in the HTML) right before that
    token's paragraph, once the email is stripped down to plain text.
    """
    sections: dict[str, str] = {}
    current_symbol = None
    buffer: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == COST_FOOTER_TITLE:
            break  # everything after this is the cost footer, not token content
        if stripped in symbols:
            if current_symbol:
                sections[current_symbol] = "\n".join(buffer).strip()
            current_symbol = stripped
            buffer = []
        elif current_symbol:
            buffer.append(line)

    if current_symbol:
        sections[current_symbol] = "\n".join(buffer).strip()

    return sections


def build_token_digests(
    config: dict, previous_sections: dict[str, str] | None = None
) -> tuple[dict[str, str], list[tuple[str, dict | None]]]:
    """
    Returns ({token_symbol: digest_paragraph}, [(token_symbol, usage_record_or_None)])
    for every token in config.
    """
    digests = {}
    usages: list[tuple[str, dict | None]] = []
    previous_sections = previous_sections or {}

    for token_cfg in config.get("monthly", {}).get("tokens", []):
        symbol = token_cfg["symbol"]
        print(f"\n=== {symbol} ===")

        all_posts = []
        for account in token_cfg.get("x_accounts", []):
            posts = fetch_x_posts(account, lookback_days=30)
            all_posts.extend(posts)
            print(f"  @{account}: {len(posts)} posts")
            time.sleep(1)  # polite pause between accounts

        digest, citation_map, usage = summarize_token_digest(
            symbol, all_posts, previous_digest=previous_sections.get(symbol)
        )
        digests[symbol] = linkify_citations(digest, citation_map)
        usages.append((symbol, usage))

    return digests, usages


def build_email_html(
    digests: dict[str, str],
    usages: list[tuple[str, dict | None]] | None = None,
    x_reads: dict | None = None,
) -> str:
    # Neutral scheme for all tokens for now -- could go per-token later
    ACCENT = "#555555"
    CARD_BG = "#f2f2f2"

    sections_html = "".join(
        render_section(symbol, ACCENT, render_cards(body, CARD_BG))
        for symbol, body in digests.items()
    )

    cost_html = render_cost_footer(usages or [], x_reads)
    cost_row = (
        f'<tr><td style="padding: 14px 8px; background-color: #fafafa; '
        f'border-top: 1px solid #eeeeee;">{cost_html}</td></tr>'
        if cost_html else ""
    )

    today_str = date.today().strftime("%B %Y")

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
                     style="background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e0e0e0; max-width: 680px;">
                <tr>
                  <td style="background-color: #111111; padding: 18px 8px;">
                    <span style="color: #ffffff; font-size: 20px; font-weight: bold; font-family: sans-serif;">
                      Crypto Monthly Digest — Small/Mid Caps
                    </span>
                    <br>
                    <span style="color: #aaaaaa; font-size: 13px; font-family: sans-serif;">
                      {today_str}
                    </span>
                  </td>
                </tr>
                <tr><td style="height: 8px;"></td></tr>

                {sections_html}

                {cost_row}
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

    monthly_cfg = config["monthly"]
    email_cfg = config["email"]

    # See weekly_job.py for why this is toggleable -- same rationale, same
    # env var. Defaults on for real/scheduled use.
    continuity_enabled = os.environ.get("DISABLE_CONTINUITY", "").lower() not in ("1", "true", "yes")

    previous_sections = {}
    if continuity_enabled:
        print("Checking for last month's digest (for continuity)...")
        previous = fetch_latest_email(f'subject:"{monthly_cfg["subject"]}"')
        if previous:
            symbols = [t["symbol"] for t in monthly_cfg.get("tokens", [])]
            previous_sections = parse_previous_digest(previous["body"], symbols)
            print(f"  found one from {previous['date']}, parsed {len(previous_sections)} token section(s)")
        else:
            print("  none found (first run?)")
    else:
        print("Continuity disabled (DISABLE_CONTINUITY set) -- skipping last digest lookup.")

    digests, usages = build_token_digests(config, previous_sections=previous_sections)

    print("\nBuilding email...")
    x_reads = estimate_x_cost(get_read_stats(), config.get("x_api_pricing"))
    html = build_email_html(digests, usages, x_reads)

    subject = f"{monthly_cfg['subject']} — {date.today().strftime('%b %Y')}"

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
