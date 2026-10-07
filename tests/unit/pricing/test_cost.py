"""Estimated API cost of one model response, from tokens and dated list prices."""

import pytest

from agent_history.pricing import PriceTable, estimate_cost, load_price_table

PRICES = PriceTable(
    {
        "claude-test": [
            {
                "from": "2026-01-01",
                "input": 5e-06,
                "output": 25e-06,
                "cache_read": 0.5e-06,
                "cache_write": 6.25e-06,
            }
        ],
        "claude-tiered": [
            {
                "from": "2026-01-01",
                "input": 3e-06,
                "output": 15e-06,
                "cache_read": 0.3e-06,
                "cache_write": 3.75e-06,
                "tiers": [
                    {
                        "above_tokens": 200000,
                        "input": 6e-06,
                        "output": 22.5e-06,
                        "cache_read": 0.6e-06,
                        "cache_write": 7.5e-06,
                    }
                ],
            }
        ],
        "gpt-test-codex": [
            {"from": "2026-03-01", "input": 1.75e-06, "output": 14e-06, "cache_read": 0.175e-06}
        ],
        "gpt-repriced": [
            {"from": "2026-07-31", "input": 5e-06, "output": 30e-06},
            {"from": "2026-08-31", "input": 4e-06, "output": 20e-06},
        ],
    }
)


def _cost(agent, model, timestamp="2026-09-15T10:00:00Z", **tokens):
    return estimate_cost(
        agent,
        model,
        timestamp,
        tokens.get("input", 0),
        tokens.get("output", 0),
        tokens.get("cache_read", 0),
        tokens.get("cache_write", 0),
        prices=PRICES,
    )


def test_claude_input_excludes_cache_tokens():
    cost = _cost(
        "claude", "claude-test", input=1000, output=2000, cache_read=10000, cache_write=3000
    )
    assert cost == pytest.approx(1000 * 5e-06 + 2000 * 25e-06 + 10000 * 0.5e-06 + 3000 * 6.25e-06)


def test_codex_input_includes_cached_tokens():
    """Codex counts cached tokens inside input; only the rest pays the full rate."""
    cost = _cost("codex", "gpt-test-codex", input=10000, output=500, cache_read=4000)
    assert cost == pytest.approx(6000 * 1.75e-06 + 4000 * 0.175e-06 + 500 * 14e-06)


def test_price_in_effect_on_the_message_date_is_used():
    before = _cost("codex", "gpt-repriced", "2026-08-15T00:00:00Z", input=1000, output=1000)
    after = _cost("codex", "gpt-repriced", "2026-09-10T00:00:00Z", input=1000, output=1000)
    assert before == pytest.approx(1000 * 5e-06 + 1000 * 30e-06)
    assert after == pytest.approx(1000 * 4e-06 + 1000 * 20e-06)


def test_message_older_than_first_listed_price_uses_first_price():
    cost = _cost("codex", "gpt-test-codex", "2026-02-10T00:00:00Z", input=1000)
    assert cost == pytest.approx(1000 * 1.75e-06)


def test_missing_timestamp_uses_latest_price():
    cost = _cost("codex", "gpt-repriced", "", output=1000)
    assert cost == pytest.approx(1000 * 20e-06)


def test_long_prompt_uses_long_context_tier():
    """The tier applies when the whole prompt, cached parts included, exceeds it."""
    cost = _cost("claude", "claude-tiered", input=1000, output=100, cache_read=250000)
    assert cost == pytest.approx(1000 * 6e-06 + 100 * 22.5e-06 + 250000 * 0.6e-06)


def test_prompt_at_tier_threshold_uses_base_prices():
    cost = _cost("claude", "claude-tiered", input=200000, output=100)
    assert cost == pytest.approx(200000 * 3e-06 + 100 * 15e-06)


def test_missing_cache_prices_fall_back_to_input_price():
    cost = _cost("claude", "gpt-repriced", cache_read=1000, cache_write=1000)
    assert cost == pytest.approx(2000 * 4e-06)


@pytest.mark.parametrize(
    "model",
    ["claude-test[1m]", "anthropic/claude-test", "claude-test-20260101", "CLAUDE-TEST"],
)
def test_model_name_variants_resolve(model):
    assert _cost("claude", model, output=1000) == pytest.approx(1000 * 25e-06)


def test_unknown_model_is_unpriced():
    assert _cost("claude", "claude-unknown", input=10, output=10) is None


def test_message_without_tokens_costs_nothing_even_without_a_price():
    assert _cost("claude", None) == 0.0
    assert _cost("claude", "<synthetic>") == 0.0


def test_bundled_price_list_prices_retired_models():
    """Models dropped from the newest list keep the price from older lists."""
    table = load_price_table()
    cost = estimate_cost(
        "claude",
        "claude-opus-4-20250514",
        "2025-08-01T00:00:00Z",
        1_000_000,
        1_000_000,
        0,
        0,
        prices=table,
    )
    assert cost == pytest.approx(15.0 + 75.0)


def test_bundled_price_list_records_its_sources():
    table = load_price_table()
    assert table.sources
    assert all(source["commit"] and source["sha256"] for source in table.sources)
