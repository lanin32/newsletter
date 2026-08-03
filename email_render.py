"""
Shared HTML rendering helpers for the digest emails -- used by both
weekly_job.py and monthly_job.py so their visual style stays in sync.
"""
import re

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
