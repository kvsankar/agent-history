#!/usr/bin/env python3
"""Regenerate agent_history/pricing/model_prices.json from LiteLLM's price list.

The source is ``model_prices_and_context_window.json`` in BerriAI/litellm. The
script reads it at the last commit before the first day of each month in a
range, so a session is priced with the list that applied in its month, and
models that were later removed from the list keep their prices. Only
Anthropic, OpenAI and Gemini chat models are kept, with their standard (not
batch, flex or priority) per-token prices and any long-context price tiers. A
model's price history records a new entry only when its prices change.

Usage:
    python scripts/update_model_prices.py --from 2025-06 [--to 2026-10]
"""

import argparse
import datetime
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = "BerriAI/litellm"
SOURCE_PATH = "model_prices_and_context_window.json"
OUTPUT = Path(__file__).resolve().parent.parent / "agent_history" / "pricing" / "model_prices.json"

PROVIDERS = {"anthropic", "openai", "gemini"}
MODES = {"chat", "responses"}
PROVIDER_PREFIXES = ("gemini/", "openai/", "anthropic/")

BASE_FIELDS = {
    "input": "input_cost_per_token",
    "output": "output_cost_per_token",
    "cache_read": "cache_read_input_token_cost",
    "cache_write": "cache_creation_input_token_cost",
}
TIER_FIELD = re.compile(r"^(?P<base>[a-z_]+)_above_(?P<k>\d+)k_tokens$")


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "cagelens-price-update"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _commit_before(date: str) -> tuple:
    url = (
        f"https://api.github.com/repos/{REPO}/commits?path={SOURCE_PATH}"
        f"&until={date}T00:00:00Z&per_page=1"
    )
    commits = json.loads(_get(url))
    if not commits:
        return None, None
    return commits[0]["sha"], commits[0]["commit"]["committer"]["date"][:10]


def _tiers(entry: dict) -> list:
    tiers: dict = {}
    for key, value in entry.items():
        match = TIER_FIELD.match(key)
        if not match or not isinstance(value, (int, float)):
            continue
        for name, base in BASE_FIELDS.items():
            if match.group("base") == base:
                threshold = int(match.group("k")) * 1000
                tiers.setdefault(threshold, {"above_tokens": threshold})[name] = value
    return [tiers[threshold] for threshold in sorted(tiers)]


def extract_prices(source: dict) -> dict:
    """Return {model: prices} for the chat models this tool can price."""
    models: dict = {}
    for key, entry in source.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("litellm_provider") not in PROVIDERS or entry.get("mode") not in MODES:
            continue
        prices = {
            name: entry[field]
            for name, field in BASE_FIELDS.items()
            if isinstance(entry.get(field), (int, float))
        }
        if "input" not in prices or "output" not in prices:
            continue
        tiers = _tiers(entry)
        if tiers:
            prices["tiers"] = tiers
        name = key
        for prefix in PROVIDER_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix) :]
        models.setdefault(name, prices)
    return models


def merge_snapshots(snapshots: list) -> dict:
    """Merge (effective_date, {model: prices}) snapshots, oldest first.

    Each model gets a list of {"from": date, ...prices}; a new entry is added
    only when the prices differ from the model's previous entry.
    """
    history: dict = {}
    for effective, models in sorted(snapshots, key=lambda item: item[0]):
        for name, prices in models.items():
            entries = history.setdefault(name, [])
            previous = {k: v for k, v in entries[-1].items() if k != "from"} if entries else None
            if prices != previous:
                entries.append({"from": effective, **prices})
    return dict(sorted(history.items()))


def _months(start: str, end: str) -> list:
    year, month = (int(part) for part in start.split("-"))
    last_year, last_month = (int(part) for part in end.split("-"))
    months = []
    while (year, month) <= (last_year, last_month):
        months.append(f"{year:04d}-{month:02d}-01")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="start", required=True, help="first month, YYYY-MM")
    parser.add_argument("--to", dest="end", help="last month, YYYY-MM (default: this month)")
    args = parser.parse_args()
    today = datetime.date.today()
    end = args.end or f"{today.year:04d}-{today.month:02d}"

    snapshots = []
    sources = []
    seen = set()
    # The month starts, plus today, so the newest list is always included.
    for date in [*_months(args.start, end), (today + datetime.timedelta(days=1)).isoformat()]:
        sha, committed = _commit_before(date)
        if not sha or sha in seen:
            continue
        seen.add(sha)
        raw = _get(f"https://raw.githubusercontent.com/{REPO}/{sha}/{SOURCE_PATH}")
        snapshots.append((committed, extract_prices(json.loads(raw))))
        sources.append(
            {
                "commit": sha,
                "committed": committed,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "url": f"https://raw.githubusercontent.com/{REPO}/{sha}/{SOURCE_PATH}",
            }
        )
        print(f"{committed} {sha}", file=sys.stderr)

    data = {
        "about": (
            "Per-token API list prices in USD, from LiteLLM's price list. "
            "Each model lists its prices from the date they took effect in the list."
        ),
        "repository": f"https://github.com/{REPO}",
        "retrieved": today.isoformat(),
        "sources": sources,
        "models": merge_snapshots(snapshots),
    }
    OUTPUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(data['models'])} models to {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
