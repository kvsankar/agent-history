"""Values from transcripts become counts and text that the stores can hold."""

from __future__ import annotations

import pytest

from agent_history.utils.jsonl import MAX_COUNT, as_count, as_text

LONE_HIGH = "\ud800"
LONE_LOW = "\udc00"


def test_the_largest_count_is_2_to_the_53() -> None:
    assert MAX_COUNT == 2**53


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0),
        (17, 17),
        ("17", 17),
        (" 12.7 ", 12),
        (12.7, 12),
        (2**53, 2**53),
        (float(2**53), 2**53),
        ("9007199254740992", 2**53),
    ],
)
def test_a_count_in_range_is_kept(value, expected) -> None:
    assert as_count(value) == expected


@pytest.mark.parametrize(
    "value",
    [-1, "-5", -0.5, 2**53 + 1, 2**64, 10**20, "1e300", 1e300, "5e18", float("inf"), "nan"],
)
def test_a_count_outside_0_to_2_to_the_53_is_0(value) -> None:
    assert as_count(value) == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (f"/home/alex/a{LONE_HIGH}b", "/home/alex/a\ufffdb"),
        (f"{LONE_LOW}x{LONE_HIGH}", "\ufffdx\ufffd"),
        ("plain \U0001f600 text", "plain \U0001f600 text"),
        ([f"a{LONE_HIGH}"], '["a\ufffd"]'),
    ],
)
def test_text_holds_no_lone_surrogates(value, expected) -> None:
    text = as_text(value)

    assert text == expected
    text.encode("utf-8")
