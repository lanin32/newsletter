"""
Turns an OpenAI Responses API `usage` object into a small record, and prices
it for the "Summarization cost" footer in the digest emails.

Pricing: OpenAI has no official pricing endpoint (the models API returns no
prices), so the live source here is LiteLLM's community-maintained price list
on GitHub -- a public JSON file keyed by model id, with per-token USD rates.
It is fetched once per run, with a short timeout. If that fails, or the model
isn't in the file, we fall back to the small table below; if that has no
entry either, the email shows tokens but no dollar figure (never a made-up one).
"""
import json
import urllib.request
from functools import lru_cache

PRICES_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

# USD per 1M tokens. Only used when the live list is unreachable or lacks the
# model -- may go stale, which is exactly why the live list is tried first.
FALLBACK_PRICES_PER_MILLION = {
    "gpt-6-luna": {"input": 0.10, "output": 0.50, "cached_input": 0.01},
    "gpt-6-sol": {"input": 2.00, "output": 10.00, "cached_input": 0.20},
    "gpt-4.1": {"input": 2.00, "output": 8.00, "cached_input": 0.50},
}


# X API pay-per-use rates, USD per resource returned. I found no pricing
# endpoint for X either, so these are overridable from config.yaml
# (`x_api_pricing:`) -- check X's pricing page if the figure ever looks off.
DEFAULT_X_PRICING = {"post_read": 0.005, "user_read": 0.010}


@lru_cache(maxsize=1)
def _load_price_table() -> dict | None:
    """Fetches the live price list once per process; None if unreachable."""
    try:
        req = urllib.request.Request(PRICES_URL, headers={"User-Agent": "crypto-newsletter-bot"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except Exception as e:
        print(f"  Could not fetch live price list ({e}) -- will use fallback prices.")
        return None


def get_prices(model: str) -> dict | None:
    """
    Returns {input, output, cached_input, source} in USD per 1M tokens, or
    None if the model's price can't be determined from any source.
    """
    table = _load_price_table()
    entry = table.get(model) if table else None
    if isinstance(entry, dict) and entry.get("input_cost_per_token") is not None \
            and entry.get("output_cost_per_token") is not None:
        input_price = entry["input_cost_per_token"] * 1_000_000
        cached = entry.get("cache_read_input_token_cost")
        return {
            "input": input_price,
            "output": entry["output_cost_per_token"] * 1_000_000,
            # no cached-input rate listed -> treat cached tokens as full price
            "cached_input": cached * 1_000_000 if cached is not None else input_price,
            "source": "LiteLLM price list",
        }

    fallback = FALLBACK_PRICES_PER_MILLION.get(model)
    if fallback:
        return {**fallback, "source": "built-in fallback prices"}
    return None


def usage_record(response, model: str, effort: str | None, mode: str | None) -> dict:
    """
    Pulls the numbers we care about out of a Responses API response.
    effort/mode are None when the reasoning param had to be dropped (models
    like gpt-4.1 that don't support it).
    """
    u = response.usage
    in_details = getattr(u, "input_tokens_details", None)
    out_details = getattr(u, "output_tokens_details", None)
    return {
        "model": model,
        "effort": effort,
        "mode": mode,
        "input_tokens": u.input_tokens,
        "cached_tokens": (getattr(in_details, "cached_tokens", 0) or 0) if in_details else 0,
        "output_tokens": u.output_tokens,  # includes hidden reasoning tokens (billed as output)
        "reasoning_tokens": (getattr(out_details, "reasoning_tokens", 0) or 0) if out_details else 0,
        "total_tokens": u.total_tokens,
    }


def estimate_cost(rec: dict) -> tuple[float | None, dict | None]:
    """Returns (cost_usd, prices_used), or (None, None) if the model has no known price."""
    prices = get_prices(rec["model"])
    if not prices:
        return None, None
    uncached_input = rec["input_tokens"] - rec["cached_tokens"]
    cost = (
        uncached_input * prices["input"]
        + rec["cached_tokens"] * prices["cached_input"]
        + rec["output_tokens"] * prices["output"]
    ) / 1_000_000
    return cost, prices


def estimate_x_cost(stats: dict, pricing: dict | None = None) -> dict:
    """
    Prices a x_fetch.get_read_stats() tally. `pricing` is the optional
    `x_api_pricing` dict from config.yaml; missing keys use the defaults.
    """
    rates = {**DEFAULT_X_PRICING, **(pricing or {})}
    posts_cost = stats["posts"] * rates["post_read"]
    users_cost = stats["users"] * rates["user_read"]
    return {
        "posts": stats["posts"],
        "users": stats["users"],
        "post_rate": rates["post_read"],
        "user_rate": rates["user_read"],
        "posts_cost": posts_cost,
        "users_cost": users_cost,
        "total": posts_cost + users_cost,
        "by_account": stats.get("by_account", {}),
    }


if __name__ == "__main__":
    # quick manual test: look up prices for the models we use
    for m in ("gpt-6-luna", "gpt-6-sol", "gpt-4.1", "not-a-model"):
        print(m, "->", get_prices(m))
