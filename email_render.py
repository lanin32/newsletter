"""
Shared HTML rendering helpers for the digest emails -- used by both
weekly_job.py and monthly_job.py so their visual style stays in sync.
"""
import re

from usage_cost import estimate_cost

# Title line of the cost footer. Also used by the jobs to cut the footer off
# the previous digest before it is fed back in as continuity context.
COST_FOOTER_TITLE = "RUN COST"



def strip_cost_footer(text: str) -> str:
    """Cuts a previous digest's plain text off at its cost footer, if it has one."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == COST_FOOTER_TITLE:
            return "\n".join(lines[:i]).rstrip()
    return text


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def render_cards(text: str, bg_color: str) -> str:
    """
    Splits text into paragraph cards with sentence-per-line formatting.
    Assumes citation links have already been applied to `text` (via
    citations.linkify_citations) before calling this.
    """
    card_blocks = []
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        sentences = [s.strip() for s in SENTENCE_SPLIT.split(chunk) if s.strip()]
        sentence_html = "".join(
            f'<p style="margin: 0 0 5px 0; color: #333333; font-size: 13px; line-height: 1.45;">{s}</p>'
            for s in sentences
        )
        card_blocks.append(
            f'<div style="background-color: {bg_color}; border-radius: 10px; '
            f'padding: 12px 14px; margin-bottom: 8px;">{sentence_html}</div>'
        )
    return "".join(card_blocks)


def render_section(title: str, accent_color: str, cards_html: str) -> str:
    """
    Full section block: spacer, title framed by thin rule lines (colored,
    centered, serif), then the card content beneath it.
    """
    return f"""
    <tr><td style="height: 16px;"></td></tr>
    <tr>
      <td style="padding: 0 8px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="padding: 8px 0; text-align: center;
                       border-top: 2px solid {accent_color}; border-bottom: 2px solid {accent_color};">
              <span style="color: {accent_color}; font-size: 22px; font-weight: bold; letter-spacing: 0.5px;
                           font-family: Georgia, 'Times New Roman', serif;">
                {title}
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>
    <tr>
      <td style="padding: 12px 8px 4px;">
        {cards_html}
      </td>
    </tr>
    """


def render_cost_footer(
    entries: list[tuple[str, dict | None]], x_reads: dict | None = None
) -> str:
    """
    Small footer describing what this run cost, in two parts:
    - LLM summarization: model, reasoning settings, token counts, estimated $.
      `entries` is a list of (label, usage_record) -- one entry for the weekly
      digest, one per token for the monthly one. Entries whose record is None
      (nothing was summarized) are skipped.
    - X API reads: posts/user lookups returned by X and their estimated $
      (`x_reads` is usage_cost.estimate_x_cost's result).
    Plus a total when both parts are priced. Returns "" if there is nothing to show.
    """
    entries = [(label, rec) for label, rec in entries if rec]
    if not entries and not (x_reads and (x_reads["posts"] or x_reads["users"])):
        return ""

    def heading(text: str) -> str:
        return f'<div style="margin-top: 8px; color: #888888;"><strong>{text}</strong></div>'

    def line(text: str) -> str:
        return f'<div style="margin-top: 3px;">{text}</div>'

    parts = []
    llm_cost = None
    llm_priced = False

    if entries:
        recs = [rec for _, rec in entries]
        costs = [estimate_cost(rec) for rec in recs]
        llm_priced = all(c is not None for c, _ in costs)
        llm_cost = sum(c for c, _ in costs) if llm_priced else None
        prices = costs[0][1]  # every call in a run uses the same model

        models = ", ".join(dict.fromkeys(r["model"] for r in recs))
        efforts = list(dict.fromkeys((r["effort"], r["mode"]) for r in recs))
        reasoning = ", ".join(
            f"{e} ({m} mode)" if e else "n/a (model has no reasoning setting)"
            for e, m in efforts
        )
        in_tok = sum(r["input_tokens"] for r in recs)
        cached = sum(r["cached_tokens"] for r in recs)
        out_tok = sum(r["output_tokens"] for r in recs)
        reasoning_tok = sum(r["reasoning_tokens"] for r in recs)
        total_tok = sum(r["total_tokens"] for r in recs)

        parts.append(heading("Summarization (LLM)"))
        if len(recs) > 1:
            parts.append(line(f"Calls: {len(recs)} (one per token)"))
        parts.append(line(f"Model: {models} &middot; reasoning effort: {reasoning}"))
        parts.append(line(
            f"Tokens: {in_tok:,} in ({cached:,} cached) &middot; "
            f"{out_tok:,} out ({reasoning_tok:,} reasoning) &middot; {total_tok:,} total"
        ))
        if llm_priced and prices:
            parts.append(line(
                f"Estimated cost: <strong>${llm_cost:.4f}</strong> "
                f"(${prices['input']:.2f} in / ${prices['output']:.2f} out per 1M tokens, "
                f"from {prices['source']})"
            ))
        else:
            parts.append(line("Estimated cost: unavailable (no price found for this model)"))
        if len(entries) > 1 and llm_priced:
            per_entry = " &middot; ".join(
                f"{label} ${c:.4f}" for (label, _), (c, _) in zip(entries, costs)
            )
            parts.append(line(f"Per token: {per_entry}"))

    x_cost = None
    if x_reads and (x_reads["posts"] or x_reads["users"]):
        x_cost = x_reads["total"]
        parts.append(heading("X API reads"))
        parts.append(line(
            f"Posts read: {x_reads['posts']:,} &times; ${x_reads['post_rate']:.3f} "
            f"= ${x_reads['posts_cost']:.2f}"
        ))
        if x_reads["users"]:
            parts.append(line(
                f"User lookups: {x_reads['users']:,} &times; ${x_reads['user_rate']:.3f} "
                f"= ${x_reads['users_cost']:.2f}"
            ))
        parts.append(line(
            f"Estimated cost: <strong>${x_cost:.2f}</strong> (X bills per resource returned; "
            f"rates from config.yaml)"
        ))
        per_account = sorted(x_reads["by_account"].items(), key=lambda kv: -kv[1])
        if per_account:
            parts.append(line(
                "Posts per account: " + " &middot; ".join(f"{u} {n:,}" for u, n in per_account)
            ))

    if x_cost is not None and llm_priced:
        parts.append(heading(f"Total: ${llm_cost + x_cost:.2f}"))
    elif x_cost is not None and entries:
        parts.append(heading(f"Total: at least ${x_cost:.2f} (LLM price unavailable)"))

    return (
        f'<span style="color: #999999; font-size: 12px; font-family: sans-serif;">{COST_FOOTER_TITLE}</span>'
        f'<div style="color: #999999; font-size: 12px; font-family: sans-serif; margin-top: 2px;">{"".join(parts)}</div>'
    )
