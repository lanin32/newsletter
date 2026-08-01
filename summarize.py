"""
Takes labeled raw material from multiple sources (newsletters, X posts, etc.)
and produces one weekly digest with three sections: BTC, ETH, General Market.

Sources are passed in as a dict, e.g.:
{
    "Milk Road (newsletter)": [ {subject, date, body}, ... ],
    "Proof of Words (newsletter)": [ {subject, date, body}, ... ],
    "Vitalik Buterin (X posts)": [ {text, date}, ... ],
    "Dan Held (X posts)": [ {text, date}, ... ],
}
The LLM sees everything at once, labeled by source, and routes each fact to
whichever section it actually belongs to -- regardless of which source it came from.
"""
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())

SYSTEM_PROMPT = """You are building a personal weekly crypto digest email from raw
material pulled from several sources -- newsletters and X (Twitter) posts. You will
be given the raw content, labeled by which source it came from.

Note on source types: newsletter content is edited, longer-form writing. X posts are
short, informal, and may be fragmentary, sarcastic, or reference things without full
context -- read them accordingly, and don't over-interpret a casual post as a formal
announcement.

Before writing anything, first make a private list of every distinct story or
fact found across all sources. Assign each one to exactly one section (BTC, ETH,
or GENERAL) based on what it's actually about. Do this assignment BEFORE drafting
any prose -- once a story is assigned to a section, it is used ONLY there.

Then write the three sections using only the stories assigned to each one:

##BTC##
<content -- see length note below>

##ETH##
<content -- see length note below>

##GENERAL##
<content -- see length note below>

Length: let the length follow the content, not a target. A section with three
solid stories might run 5-6 sentences; a section with one story might be 2 sentences;
a section with nothing left after other sections claimed their stories should be
1 sentence saying so. Do NOT pad a short section by restating a story that's already
used in a different section, and do NOT treat sentence count as a goal to hit.

Routing rules:
- Route each fact to whichever section it is actually ABOUT, regardless of which
  source it came from. A newsletter can contain an ETH-specific story -- that goes
  in ETH, not General. An X post from a BTC-focused account might comment on the
  broader market -- that goes in General, not BTC.
- HARD RULE: every distinct story or fact appears in EXACTLY ONE section, full stop.
  This is the single most important rule -- violating it (mentioning the same story
  in two sections, even briefly, even with different wording or framing) is a failure
  regardless of how good the prose otherwise reads.
- If a story touches both a specific token and the general market (e.g. "Company X
  launches a product on Ethereum, reflecting a broader institutional trend"), put
  the WHOLE story in the more specific section (ETH), not split across both, and not
  duplicated in General with a rephrased "broader trend" framing.
- If the same fact appears in multiple input sources, that's still just one fact --
  mention it once, in its one section.

Example of what NOT to do: if BlackRock/Fidelity/Coinbase form a Bitcoin security
consortium, that goes in BTC only. Do not also mention it in General as an example
of "growing institutional collaboration." If Robinhood launches an Ethereum L2,
that goes in ETH only. Do not also mention it in General as an example of "mainstream
platforms expanding crypto offerings." Pick the one section, say it once, move on.

Content priorities (apply to all three sections):
- Prioritize adoption: institutional interest, real-world usage, regulatory
  developments, partnerships, ETF/treasury activity, ecosystem growth.
- Development and protocol updates are fine to include but secondary to adoption.
- Explicitly avoid price predictions, technical analysis, and short-term price
  commentary. If a price move is itself newsworthy (e.g. an ETF approval caused
  a jump), describe the event, not the chart.

Style:
- Plain prose, no bullet points, no sub-headers within a section
- No fluff, no "in conclusion", no restating that this is a summary
"""


def _format_sources(sources: dict[str, list[dict]]) -> str:
    blocks = []
    for source_name, items in sources.items():
        if not items:
            continue
        item_texts = []
        for item in items:
            if "subject" in item:  # newsletter email
                item_texts.append(
                    f"[{item.get('date', '')}] Subject: {item['subject']}\n{item['body']}"
                )
            elif "username" in item:  # X post
                item_texts.append(f"[{item.get('date', '')}] {item['text']}")
            else:
                item_texts.append(str(item))
        blocks.append(f"=== {source_name} ===\n" + "\n\n".join(item_texts))
    return "\n\n".join(blocks)


def summarize_weekly_digest(sources: dict[str, list[dict]]) -> dict[str, str]:
    """
    Returns {"btc": "...", "eth": "...", "general": "..."}.
    """
    formatted = _format_sources(sources)

    if not formatted.strip():
        empty = "No notable news found for this week."
        return {"btc": empty, "eth": empty, "general": empty}

    response = client.chat.completions.create(
        model="gpt-4.1",
        max_tokens=1200,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": formatted},
        ],
    )

    text = response.choices[0].message.content

    sections = {"btc": "", "eth": "", "general": ""}
    current_key = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "##BTC##":
            current_key = "btc"
        elif stripped == "##ETH##":
            current_key = "eth"
        elif stripped == "##GENERAL##":
            current_key = "general"
        elif current_key:
            sections[current_key] += line + "\n"

    return {k: v.strip() for k, v in sections.items()}


if __name__ == "__main__":
    import yaml
    from gmail_fetch import fetch_newsletter_emails
    from x_fetch import fetch_x_posts

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    sources = {}

    for nl in config.get("newsletters", []):
        if "REPLACE_ME" in nl["gmail_query"]:
            print(f"Skipping {nl['name']} -- gmail_query not configured yet")
            continue
        print(f"Fetching {nl['name']}...")
        emails = fetch_newsletter_emails(nl["gmail_query"], lookback_days=nl["lookback_days"])
        sources[f"{nl['name']} (newsletter)"] = emails
        print(f"  found {len(emails)} emails")

    for token, accounts in config.get("x_accounts", {}).items():
        for account in accounts:
            print(f"Fetching @{account} ({token})...")
            posts = fetch_x_posts(account, lookback_days=7)
            sources[f"{account} (X posts)"] = posts
            print(f"  found {len(posts)} posts")

    print("\nSummarizing...")
    digest = summarize_weekly_digest(sources)

    for section in ["btc", "eth", "general"]:
        print(f"\n=== {section.upper()} ===")
        print(digest[section])
