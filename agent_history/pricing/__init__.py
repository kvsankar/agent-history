"""Estimated API cost of model responses, from token counts and list prices.

The estimate is what the tokens would cost at the provider's pay-as-you-go
API list prices on the day they were used. It is not what a subscription
plan charged. Prices come from ``model_prices.json``, which
``scripts/update_model_prices.py`` builds from monthly snapshots of LiteLLM's
price list and which records the commits it read.

Known gaps: batch, flex and priority rates, Anthropic's one-hour cache-write
rate and fast-mode surcharges are not applied; the standard rates are.
"""

import bisect
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_FILE = Path(__file__).with_name("model_prices.json")
_PROVIDER_PREFIX = re.compile(r"^(?:anthropic|openai|gemini|models)/")
_SUFFIX = re.compile(r"\[[^\]]*\]$")
_DATE_SUFFIX = re.compile(r"-\d{8}$")

# Agents whose input token count already includes the cached tokens.
_INPUT_INCLUDES_CACHE_READ = {"codex"}


class PriceTable:
    """Price history per model: a list of {"from": date, ...prices}, oldest first."""

    def __init__(self, models: Dict[str, List[Dict[str, Any]]], sources: Optional[list] = None):
        self._models = {name.lower(): entries for name, entries in models.items()}
        self._dates = {
            name: [entry["from"] for entry in entries] for name, entries in self._models.items()
        }
        self.sources = sources or []

    def resolve(self, model: str) -> Optional[str]:
        """Return the table's name for a model as agents write it, or None."""
        name = _SUFFIX.sub("", model.strip().lower())
        name = _PROVIDER_PREFIX.sub("", name)
        if name in self._models:
            return name
        undated = _DATE_SUFFIX.sub("", name)
        if undated in self._models:
            return undated
        return None

    def prices(self, model: str, timestamp: str) -> Optional[Dict[str, Any]]:
        """Return the prices in effect for a model at a timestamp, or None."""
        name = self.resolve(model)
        if name is None:
            return None
        entries = self._models[name]
        if not timestamp:
            return entries[-1]
        index = bisect.bisect_right(self._dates[name], timestamp[:10]) - 1
        return entries[max(index, 0)]


@lru_cache(maxsize=1)
def load_price_table() -> PriceTable:
    """Load the bundled price history."""
    data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return PriceTable(data["models"], data.get("sources"))


def _tier_prices(prices: Dict[str, Any], prompt_tokens: int) -> Dict[str, Any]:
    effective = dict(prices)
    for tier in prices.get("tiers", []):
        if prompt_tokens > tier["above_tokens"]:
            effective.update({key: value for key, value in tier.items() if key != "above_tokens"})
    return effective


def estimate_cost(
    agent: Optional[str],
    model: Optional[str],
    timestamp: Optional[str],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    cache_read_tokens: Optional[int],
    cache_creation_tokens: Optional[int],
    prices: Optional[PriceTable] = None,
) -> Optional[float]:
    """Return the estimated USD cost of one response, or None if unpriced.

    A response with no tokens costs 0.0 whether or not its model is known.
    """
    input_tokens = input_tokens or 0
    output_tokens = output_tokens or 0
    cache_read_tokens = cache_read_tokens or 0
    cache_creation_tokens = cache_creation_tokens or 0
    if not (input_tokens or output_tokens or cache_read_tokens or cache_creation_tokens):
        return 0.0
    if not model:
        return None

    table = prices or load_price_table()
    found = table.prices(model, timestamp or "")
    if found is None:
        return None

    uncached_input = input_tokens
    if (agent or "").lower() in _INPUT_INCLUDES_CACHE_READ:
        uncached_input = max(input_tokens - cache_read_tokens, 0)
    prompt_tokens = uncached_input + cache_read_tokens + cache_creation_tokens
    rates = _tier_prices(found, prompt_tokens)

    input_rate = rates["input"]
    return (
        uncached_input * input_rate
        + output_tokens * rates["output"]
        + cache_read_tokens * rates.get("cache_read", input_rate)
        + cache_creation_tokens * rates.get("cache_write", input_rate)
    )
