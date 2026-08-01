"""
Summarizes one obscure token's X activity for the month into a single
paragraph. Called once per token -- no pooling across tokens, since there's
no cross-project routing/dedup problem to solve (unlike the weekly digest).
"""
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())

SYSTEM_PROMPT = """You are building a personal monthly digest of a single, smaller
crypto project's activity, based on that project's own X (Twitter) accounts (team
members, official account, etc.) over the past month.

Note: X posts are short, informal, and may be fragmentary or reference things
without full context -- read them accordingly.

Write a single digest paragraph, 4-8 sentences depending on how much happened:
- Cover what actually happened: development progress, releases, partnerships,
  adoption signals, community milestones -- for a smaller project, development
  updates ARE often the news, so don't deprioritize them the way a mature/major
  token's coverage might.
- Routine low-signal content -- memes, generic community banter, polls, giveaways,
  engagement posts with no actual news in them -- should NOT be described in
  detail just because it exists. If that's most or all of what was posted, say so
  in ONE sentence ("It was a quiet month, mostly memes and community engagement
  posts, with no major updates") and move on. Do not narrate what the memes were
  about, what the polls asked, or list out routine promotional content.
- Genuinely relevant information is worth including even if it's not about the
  project directly -- e.g. major news about a close competitor, a security
  incident affecting the same ecosystem/chain, or sector-wide news the project's
  own accounts discussed or were implicated in. Use judgment: relevant means it
  actually matters to someone tracking this project, not just that it was
  mentioned somewhere in the source material.
- Explicitly avoid price predictions, technical analysis, and short-term price
  commentary. If a price move is itself newsworthy (e.g. a major exchange listing
  caused it), describe the event, not the chart.
- Plain prose, no bullet points, no headers.
- No fluff, no "in conclusion", no restating that this is a summary.
- If genuinely nothing noteworthy happened this month, say so in one sentence
  rather than padding.

If a "PREVIOUS MONTH'S DIGEST FOR THIS PROJECT" block is included, use it only
for continuity -- don't repeat old news as if it's new this month. A genuine
follow-up can be mentioned briefly (e.g. "following up on last month's testnet
launch...").
"""


def _format_posts(posts: list[dict]) -> str:
    if not posts:
        return ""
    return "\n\n".join(
        f"[{p.get('date', '')}] @{p['username']}: {p['text']}"
        for p in posts
    )


def summarize_token_digest(
    token_symbol: str, posts: list[dict], previous_digest: str | None = None
) -> str:
    formatted = _format_posts(posts)

    if not formatted.strip():
        return "No notable activity found this month."

    user_content = f"Project: {token_symbol}\n\n{formatted}"
    if previous_digest:
        user_content = (
            f"=== PREVIOUS MONTH'S DIGEST FOR THIS PROJECT ===\n{previous_digest}\n\n"
            f"=== THIS MONTH'S RAW MATERIAL ===\n{formatted}"
        )

    response = client.chat.completions.create(
        model="gpt-4.1",
        max_tokens=400,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )

    return response.choices[0].message.content.strip()


if __name__ == "__main__":
    from x_fetch import fetch_x_posts

    # quick manual test -- edit these to try a specific token/account
    symbol = "AKT"
    username = "akashnet_"

    posts = fetch_x_posts(username, lookback_days=30)
    print(f"Found {len(posts)} posts from @{username}\n")

    digest = summarize_token_digest(symbol, posts)
    print(f"=== {symbol} ===\n{digest}")
