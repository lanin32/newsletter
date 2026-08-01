"""
Shared helper for turning [N] citation markers (produced by the summarizers)
into real clickable links, using a citation map built during summarization.
"""
import re


def linkify_citations(text: str, citation_map: dict[int, str]) -> str:
    def replace(match: re.Match) -> str:
        num = int(match.group(1))
        url = citation_map.get(num)
        if not url:
            return match.group(0)  # no mapping for this number -- leave it as plain text
        return f'<a href="{url}" style="color: #888888; text-decoration: none;">[{num}]</a>'

    return re.sub(r"\[(\d+)\]", replace, text)
