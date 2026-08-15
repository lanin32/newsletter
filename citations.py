"""
Shared helper for turning [N] citation markers (produced by the summarizers)
into real clickable links, using a citation map built during summarization.
"""
import re


def linkify_citations(text: str, citation_map: dict[int, str]) -> str:
    def replace(match: re.Match) -> str:
        # normally just one number, e.g. "3" -- but tolerate the model
        # occasionally bundling several into one group, e.g. "2, 4, 5",
        # by emitting one linked marker per number instead of leaving the
        # whole group unlinked
        nums = [int(n) for n in re.findall(r"\d+", match.group(1))]
        out = []
        for num in nums:
            url = citation_map.get(num)
            if url:
                out.append(f'<a href="{url}" style="color: #888888; text-decoration: none;">[{num}]</a>')
            else:
                out.append(f"[{num}]")  # no mapping for this number -- leave it as plain text
        return "".join(out)

    return re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", replace, text)
