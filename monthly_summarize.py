"""
Summarizes one obscure token's X activity for the month. Called once per
token -- no pooling across tokens, since there's no cross-project routing/
dedup problem to solve (unlike the weekly digest).
"""
import os
from openai import OpenAI

from usage_cost import usage_record

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())

# See weekly_summarize.py for the reasoning behind this switch. Override
# locally for comparison, e.g.: SUMMARIZE_MODEL=gpt-4.1 python monthly_job.py
MODEL = os.environ.get("SUMMARIZE_MODEL", "gpt-6-luna")
# Override for testing without a code edit, e.g.:
# REASONING_EFFORT=medium python monthly_job.py
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "low")
# See weekly_summarize.py for details on both of these.
REASONING_MODE = os.environ.get("REASONING_MODE", "standard")
ENABLE_REASONING_SUMMARY = os.environ.get("ENABLE_REASONING_SUMMARY", "true").lower() not in ("0", "false", "no")

SYSTEM_PROMPT = """You are building a personal monthly digest of a single, smaller
crypto project's activity, based on that project's own X (Twitter) accounts (team
members, official account, etc.) over the past month.

Note: X posts are short, informal, and may be fragmentary or reference things
without full context -- read them accordingly.

Write the digest, 4-8 sentences depending on how much happened:
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
- If there's enough distinct material to group (e.g. development news vs.
  community/ecosystem news), split into separate paragraphs with a blank line
  between them. Most months this will be short enough to stay as one paragraph
  -- only split when there's genuinely enough to group.
- If genuinely nothing noteworthy happened this month, say so in one sentence
  rather than padding.

If a "PREVIOUS MONTH'S DIGEST FOR THIS PROJECT" block is included, use it only
for continuity -- don't repeat old news as if it's new this month. A genuine
follow-up can be mentioned briefly (e.g. "following up on last month's testnet
launch...").

Citations:
- Each X post in the raw material is tagged with a citation number, like
  "(citation #7)". When a sentence draws on that post, add [7] right after
  the sentence (inside the punctuation is fine, e.g. "...happened this month [7].").
- If several consecutive sentences all draw from the SAME citation number,
  only add it once, after the last of those sentences -- not after every
  single sentence.
- If a single sentence draws on multiple DIFFERENT citation numbers, give each
  its own bracket immediately after one another, e.g. "...happened this month
  [2][4][5]." -- never combine them into one bracket like "[2, 4, 5]".
- Citation numbers only apply to THIS MONTH'S raw material. If a "PREVIOUS
  MONTH'S DIGEST" block is present for continuity, anything drawn from it
  should NOT get a citation number (it doesn't have one).
"""


def _format_posts(posts: list[dict]) -> tuple[str, dict[int, str]]:
    """
    Returns (formatted_text, citation_map). citation_map maps citation
    number -> tweet URL.
    """
    if not posts:
        return "", {}

    citation_map: dict[int, str] = {}
    lines = []
    for i, p in enumerate(posts, start=1):
        citation_map[i] = f"https://x.com/{p['username']}/status/{p['id']}"
        lines.append(f"[{p.get('date', '')}] (citation #{i}) @{p['username']}: {p['text']}")

    return "\n\n".join(lines), citation_map


def summarize_token_digest(
    token_symbol: str, posts: list[dict], previous_digest: str | None = None
) -> tuple[str, dict[int, str], dict | None]:
    """
    Returns (digest_paragraph, citation_map, usage). usage is a
    usage_cost.usage_record dict (None when there were no posts, so no call was made).
    """
    formatted, citation_map = _format_posts(posts)

    if not formatted.strip():
        return "No notable activity found this month.", {}, None

    user_content = f"Project: {token_symbol}\n\n{formatted}"
    if previous_digest:
        user_content = (
            f"=== PREVIOUS MONTH'S DIGEST FOR THIS PROJECT ===\n{previous_digest}\n\n"
            f"=== THIS MONTH'S RAW MATERIAL ===\n{formatted}"
        )

    reasoning_config = {"effort": REASONING_EFFORT, "mode": REASONING_MODE}
    if ENABLE_REASONING_SUMMARY:
        reasoning_config["summary"] = "auto"

    input_items = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    create_kwargs = dict(model=MODEL, max_output_tokens=25000, reasoning=reasoning_config, input=input_items)

    try:
        response = client.responses.create(**create_kwargs)
    except Exception as e:
        err = str(e).lower()
        # See weekly_summarize.py: unverified orgs get a 400 on the
        # "summary" param specifically -- fall back rather than fail.
        if ENABLE_REASONING_SUMMARY and "summary" in err and "verif" in err:
            print(f"  Reasoning summary unavailable (org not verified) -- retrying without it ({token_symbol}).")
            reasoning_config.pop("summary", None)
            create_kwargs["reasoning"] = reasoning_config
            response = client.responses.create(**create_kwargs)
        # Non-reasoning models (e.g. gpt-4.1) may reject "reasoning" outright.
        elif "reasoning" in err and ("unsupported" in err or "not supported" in err or "unknown" in err):
            print(f"  Model {MODEL} doesn't support the reasoning param -- retrying without it ({token_symbol}).")
            create_kwargs.pop("reasoning", None)
            response = client.responses.create(**create_kwargs)
        else:
            raise

    reasoning_used = "reasoning" in create_kwargs  # False if the fallback dropped it
    usage_rec = usage_record(
        response, MODEL,
        REASONING_EFFORT if reasoning_used else None,
        REASONING_MODE if reasoning_used else None,
    )
    usage = response.usage
    reasoning_tokens = usage.output_tokens_details.reasoning_tokens if usage.output_tokens_details else None
    print(
        f"  Usage ({token_symbol}) -- model: {MODEL}, reasoning_effort: {REASONING_EFFORT}, reasoning_mode: {REASONING_MODE}, "
        f"input: {usage.input_tokens}, output: {usage.output_tokens} "
        f"(of which reasoning: {reasoning_tokens}), total: {usage.total_tokens}"
    )

    for item in response.output:
        if item.type == "reasoning" and item.summary:
            for s in item.summary:
                print(f"  Reasoning summary ({token_symbol}): {s.text}")

    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else "unknown"
        print(f"  WARNING: response incomplete ({reason}) for {token_symbol}")

    text = response.output_text
    if not text:
        print(f"  WARNING: empty response content for {token_symbol}")
        text = ""

    return text.strip(), citation_map, usage_rec


if __name__ == "__main__":
    from x_fetch import fetch_x_posts

    # quick manual test -- edit these to try a specific token/account
    symbol = "AKT"
    username = "akashnet"

    posts = fetch_x_posts(username, lookback_days=30)
    print(f"Found {len(posts)} posts from @{username}\n")

    digest, citation_map, _usage = summarize_token_digest(symbol, posts)
    print(f"=== {symbol} ===\n{digest}")
    print(f"\n=== CITATIONS ({len(citation_map)}) ===")
    for num, url in citation_map.items():
        print(f"[{num}] {url}")
