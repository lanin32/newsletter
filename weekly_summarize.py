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

# Switched from gpt-4.1 (30k TPM on our account tier, which this request
# regularly exceeded) to gpt-5.6-luna: ~10x cheaper, newer generation, and
# a much higher TPM ceiling. Override locally for a side-by-side comparison
# without editing code, e.g.: SUMMARIZE_MODEL=gpt-4.1 python weekly_job.py
MODEL = os.environ.get("SUMMARIZE_MODEL", "gpt-6-luna")
# "low" is OpenAI's own recommendation for "simple summaries, routing,
# straightforward generation" (which matches this task), but there are
# documented reports of Luna-tier models silently truncating/emptying long,
# strictly-structured completions at low effort -- exactly this task's shape
# (long pooled input, one long delimited multi-section response). Override
# for testing without a code edit, e.g.: REASONING_EFFORT=medium python weekly_job.py
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "low")
# "standard" is the default/only option Chat Completions effectively used;
# "pro" triggers deeper multi-pass reasoning before a single final answer,
# intended for quality-first tasks. Independent of REASONING_EFFORT. Override:
# REASONING_MODE=pro python weekly_job.py
REASONING_MODE = os.environ.get("REASONING_MODE", "standard")
# Reasoning summaries are a natural-language paraphrase of the model's
# internal reasoning -- purely informational, no effect on the actual
# answer. Requires the OpenAI org to be verified or every call 400s; we
# detect that specific failure below and fall back to no summary rather
# than crash the job. Disable with ENABLE_REASONING_SUMMARY=false.
ENABLE_REASONING_SUMMARY = os.environ.get("ENABLE_REASONING_SUMMARY", "true").lower() not in ("0", "false", "no")

SYSTEM_PROMPT = """You are building a personal weekly crypto digest email from raw
material pulled from several sources -- newsletters and X (Twitter) posts. You will
be given the raw content, labeled by which source it came from.

Note on source types: newsletter content is edited, longer-form writing. X posts are
short, informal, and may be fragmentary, sarcastic, or reference things without full
context -- read them accordingly, and don't over-interpret a casual post as a formal
announcement.

If a "LAST WEEK'S DIGEST" block is included before this week's raw material, use it
only for continuity -- don't restate anything from it as if it's new this week. If
something is a genuine follow-up or update to what was reported last week, you can
say so briefly (e.g. "following up on last week's X..."), but the bulk of each
section should be this week's actual new material.

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
- No fluff, no "in conclusion", no restating that this is a summary,
  but also do not just skip stories that are relevant.
- Within each section, group related stories into separate paragraphs, with a
  blank line between paragraphs -- don't write one continuous block. For
  example, institutional/corporate news might be one paragraph, regulatory
  developments another, macro factors another. A section with only one or two
  stories can stay as a single paragraph; only split when there's enough
  distinct material to actually group.

Citations:
- Each X post in the raw material is tagged with a citation number, like
  "(citation #7)". When a sentence draws on that post, add [7] right after
  the sentence (inside the punctuation is fine, e.g. "...happened this week [7].").
- If several consecutive sentences all draw from the SAME citation number,
  only add it once, after the last of those sentences -- not after every
  single sentence.
- If a single sentence draws on multiple DIFFERENT citation numbers, give each
  its own bracket immediately after one another, e.g. "...happened this week
  [2][4][5]." -- never combine them into one bracket like "[2, 4, 5]".
- Only cite items that are explicitly tagged with a citation number (marked
  "(citation #N)" in the raw material). Some newsletter emails have one, some
  don't (depends whether a link to the original could be found) -- if an item
  has no citation number, don't invent one or attach a citation to it.
- Citation numbers only apply to THIS WEEK'S raw material. If a "LAST WEEK'S
  DIGEST" block is present for continuity, anything drawn from it should NOT
  get a citation number (it doesn't have one).
"""


def _format_sources(sources: dict[str, list[dict]]) -> tuple[str, list[dict]]:
    """
    Returns (formatted_text, items_meta). items_meta is an ordered list of
    {source_name, label, url, citation_num} dicts, one per item across all
    sources -- used both to build the citation link map and to render a
    "Sources this week" footer with numbers/links that match the inline
    citations exactly. citation_num and url are None for items with no
    citation (e.g. a newsletter with no "view online" link found).
    """
    blocks = []
    items_meta: list[dict] = []
    next_citation_num = 1

    for source_name, items in sources.items():
        if not items:
            continue
        item_texts = []
        for item in items:
            if "subject" in item:  # newsletter email
                url = item.get("url")
                num = None
                if url:
                    num = next_citation_num
                    next_citation_num += 1
                    item_texts.append(
                        f"[{item.get('date', '')}] (citation #{num}) "
                        f"Subject: {item['subject']}\n{item['body']}"
                    )
                else:
                    item_texts.append(
                        f"[{item.get('date', '')}] Subject: {item['subject']}\n{item['body']}"
                    )
                items_meta.append({
                    "source_name": source_name, "label": item["subject"],
                    "url": url, "citation_num": num,
                })
            elif "username" in item:  # X post
                num = next_citation_num
                next_citation_num += 1
                url = f"https://x.com/{item['username']}/status/{item['id']}"
                label = item["text"][:80] + ("..." if len(item["text"]) > 80 else "")
                item_texts.append(f"[{item.get('date', '')}] (citation #{num}) {item['text']}")
                items_meta.append({
                    "source_name": source_name, "label": label,
                    "url": url, "citation_num": num,
                })
            else:
                item_texts.append(str(item))
        blocks.append(f"=== {source_name} ===\n" + "\n\n".join(item_texts))

    return "\n\n".join(blocks), items_meta


def summarize_weekly_digest(
    sources: dict[str, list[dict]], previous_digest: str | None = None
) -> tuple[dict[str, str], list[dict]]:
    """
    Returns ({"btc": "...", "eth": "...", "general": "..."}, items_meta).
    items_meta is the same structure _format_sources returns -- used to
    build the citation link map and the sources footer.
    previous_digest, if given, is last week's full digest text -- passed in
    so the model can maintain continuity (avoid re-reporting old news as new,
    reference something as a follow-up) rather than treating each week in
    isolation.
    """
    formatted, items_meta = _format_sources(sources)

    if not formatted.strip():
        empty = "No notable news found for this week."
        return {"btc": empty, "eth": empty, "general": empty}, []

    user_content = formatted
    if previous_digest:
        user_content = (
            f"=== LAST WEEK'S DIGEST (for continuity -- do not repeat this as if "
            f"it's new; you may reference it as background for a follow-up) ===\n"
            f"{previous_digest}\n\n"
            f"=== THIS WEEK'S RAW MATERIAL ===\n{formatted}"
        )

    reasoning_config = {"effort": REASONING_EFFORT, "mode": REASONING_MODE}
    if ENABLE_REASONING_SUMMARY:
        reasoning_config["summary"] = "auto"

    input_items = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    # OpenAI's own guidance: reserve at least 25,000 tokens for reasoning +
    # output when starting out with these models -- our old 10,000 cap is
    # likely why xhigh ran out of budget before producing any visible text.
    create_kwargs = dict(model=MODEL, max_output_tokens=25000, reasoning=reasoning_config, input=input_items)

    try:
        response = client.responses.create(**create_kwargs)
    except Exception as e:
        err = str(e).lower()
        # Reasoning summaries require org verification; an unverified org
        # gets a 400 on the "summary" param specifically. Fall back to no
        # summary rather than fail the whole run over an optional extra.
        if ENABLE_REASONING_SUMMARY and "summary" in err and "verif" in err:
            print("  Reasoning summary unavailable (org not verified) -- retrying without it.")
            print("  To enable it: https://platform.openai.com/settings/organization/general")
            reasoning_config.pop("summary", None)
            create_kwargs["reasoning"] = reasoning_config
            response = client.responses.create(**create_kwargs)
        # Non-reasoning models (e.g. gpt-4.1) may reject the "reasoning"
        # param outright -- drop it entirely and retry rather than fail.
        elif "reasoning" in err and ("unsupported" in err or "not supported" in err or "unknown" in err):
            print(f"  Model {MODEL} doesn't support the reasoning param -- retrying without it.")
            create_kwargs.pop("reasoning", None)
            response = client.responses.create(**create_kwargs)
        else:
            raise

    usage = response.usage
    reasoning_tokens = usage.output_tokens_details.reasoning_tokens if usage.output_tokens_details else None
    print(
        f"  Usage -- model: {MODEL}, reasoning_effort: {REASONING_EFFORT}, reasoning_mode: {REASONING_MODE}, "
        f"input: {usage.input_tokens}, output: {usage.output_tokens} "
        f"(of which reasoning: {reasoning_tokens}), total: {usage.total_tokens}"
    )

    for item in response.output:
        if item.type == "reasoning" and item.summary:
            for s in item.summary:
                print(f"  Reasoning summary: {s.text}")

    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else "unknown"
        print(f"  WARNING: response incomplete ({reason}) -- consider raising max_output_tokens further")

    text = response.output_text
    if not text:
        print("  WARNING: empty response content -- see the known Luna-tier issue with long structured completions")
        text = ""

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

    return {k: v.strip() for k, v in sections.items()}, items_meta


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

    for account in config.get("x_accounts", []):
        if isinstance(account, dict):
            username = account["username"]
            phrases = account.get("phrases", [])
        else:
            username = account
            phrases = []
        print(f"Fetching @{username}...")
        posts = fetch_x_posts(username, lookback_days=7, phrases=phrases)
        sources[f"{username} (X posts)"] = posts
        print(f"  found {len(posts)} posts")

    print("\nSummarizing...")
    digest, items_meta = summarize_weekly_digest(sources)

    for section in ["btc", "eth", "general"]:
        print(f"\n=== {section.upper()} ===")
        print(digest[section])

    cited = [m for m in items_meta if m["citation_num"] is not None]
    print(f"\n=== CITATIONS ({len(cited)}) ===")
    for m in cited:
        print(f"[{m['citation_num']}] {m['label']} -- {m['url']}")
