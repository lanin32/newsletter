"""
The monthly job: for each configured small-cap token, fetches its X accounts'
posts over the past month, summarizes each token independently (no pooling --
see monthly_summarize.py for why), builds one email with a section per token,
and sends it.

Usage:
    python monthly_job.py
"""
from datetime import date
import time
import yaml

from x_fetch import fetch_x_posts
from monthly_summarize import summarize_token_digest
from gmail_send import send_email


def build_token_digests(config: dict) -> dict[str, str]:
    """
    Returns {token_symbol: digest_paragraph} for every token in config.
    """
    digests = {}

    for token_cfg in config.get("monthly", {}).get("tokens", []):
        symbol = token_cfg["symbol"]
        print(f"\n=== {symbol} ===")

        all_posts = []
        for account in token_cfg.get("x_accounts", []):
            posts = fetch_x_posts(account, lookback_days=30)
            all_posts.extend(posts)
            print(f"  @{account}: {len(posts)} posts")
            time.sleep(1)  # polite pause between accounts

        digest = summarize_token_digest(symbol, all_posts)
        digests[symbol] = digest

    return digests


def build_email_html(digests: dict[str, str]) -> str:
    def section(symbol: str, body: str) -> str:
        return f"""
        <tr>
          <td style="padding: 20px 32px; border-left: 4px solid #888888;">
            <h2 style="margin: 0 0 10px 0; font-size: 17px; color: #111111; font-family: sans-serif;">
              {symbol}
            </h2>
            <p style="margin: 0; color: #333333; font-size: 14px; line-height: 1.6; font-family: sans-serif;">
              {body}
            </p>
          </td>
        </tr>
        """

    sections_html = "".join(section(symbol, body) for symbol, body in digests.items())

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
                  <td style="padding: 20px 32px; background-color: #1a1a1a;">
                    <h1 style="margin: 0; font-size: 18px; color: #ffffff; font-family: sans-serif;">
                      Crypto Monthly Digest — Small Caps
                    </h1>
                    <span style="color: #aaaaaa; font-size: 12px; font-family: sans-serif;">
                      {date.today().strftime('%B %Y')}
                    </span>
                  </td>
                </tr>
                {sections_html}
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

    digests = build_token_digests(config)

    print("\nBuilding email...")
    html = build_email_html(digests)

    monthly_cfg = config["monthly"]
    email_cfg = config["email"]
    subject = f"{monthly_cfg['subject']} — {date.today().strftime('%b %Y')}"

    print(f"Sending to {email_cfg['to']}...")
    send_email(to=email_cfg["to"], subject=subject, body_html=html)
    print("Done.")


if __name__ == "__main__":
    main()
