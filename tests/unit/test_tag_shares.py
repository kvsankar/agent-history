"""Tag rollups: each row's share of the scope, totals that count sessions once,
and a tag facet that folds every other tag into "other"."""

from __future__ import annotations

import json

import pytest

from agent_history.cli.orchestrator import CommandOrchestrator
from tests.unit.test_cached_stats import _insert_cached_session

# Input tokens per workspace. The shared project carries both work and personal.
WORK, PERSONAL, SHARED, CLIENT, UNTAGGED = 100, 300, 50, 20, 30
TOTAL = WORK + PERSONAL + SHARED + CLIENT + UNTAGGED


@pytest.fixture
def tagged_home(tmp_path, monkeypatch):
    config_dir = tmp_path / ".cagelens"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "homes": [],
                "sources": [],
                "projects": {
                    "office": {"local": ["/tmp/office"]},
                    "hobby": {"local": ["/tmp/hobby"]},
                    "shared": {"local": ["/tmp/shared"]},
                    "consulting": {"local": ["/tmp/consulting"]},
                    "loose": {"local": ["/tmp/loose"]},
                },
                "project_tags": {
                    "office": ["work"],
                    "hobby": ["personal"],
                    "shared": ["work", "personal"],
                    "consulting": ["client"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(config_dir))
    monkeypatch.chdir(tmp_path)
    for name, tokens in [
        ("office", WORK),
        ("hobby", PERSONAL),
        ("shared", SHARED),
        ("consulting", CLIENT),
        ("loose", UNTAGGED),
    ]:
        _insert_cached_session(
            file_path=f"/tmp/{name}.jsonl",
            session_id=name,
            workspace=f"/tmp/{name}",
            input_tokens=tokens,
        )
    return tmp_path


def _run(capsys, *args):
    exit_code = CommandOrchestrator().run(["stats", "rollup", *args])
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    return captured.out


def _json_rows(capsys, *args):
    rows = json.loads(_run(capsys, *args, "--format", "json", "--raw"))
    return {row["tag"]: row for row in rows}


def test_tag_rows_carry_their_share_of_the_scope(tagged_home, capsys):
    rows = _json_rows(capsys, "--metric", "tokens", "--by", "tag")

    assert rows["work"]["share"] == pytest.approx((WORK + SHARED) / TOTAL)
    assert rows["personal"]["share"] == pytest.approx((PERSONAL + SHARED) / TOTAL)
    assert rows["untagged"]["share"] == pytest.approx(UNTAGGED / TOTAL)


def test_overlapping_tags_can_share_more_than_the_whole(tagged_home, capsys):
    rows = _json_rows(capsys, "--metric", "tokens", "--by", "tag")

    assert sum(row["share"] for row in rows.values()) == pytest.approx((TOTAL + SHARED) / TOTAL)


def test_total_row_counts_each_session_once(tagged_home, capsys):
    lines = _run(capsys, "--metric", "tokens", "--by", "tag", "--format", "tsv", "--raw")

    header, *body = lines.splitlines()
    columns = header.split("\t")
    total = dict(zip(columns, body[-1].split("\t")))
    assert total["TAG"] == "TOTAL"
    assert total["INPUT_TOKENS"] == str(TOTAL)
    assert total["SHARE"] == "100.0%"


def test_tag_facet_folds_other_tags_and_untagged_into_other(tagged_home, capsys):
    rows = _json_rows(capsys, "--metric", "tokens", "--by", "tag", "--tag-facet", "work,personal")

    assert set(rows) == {"work", "personal", "other"}
    assert rows["work"]["input_tokens"] == WORK + SHARED
    assert rows["personal"]["input_tokens"] == PERSONAL + SHARED
    assert rows["other"]["input_tokens"] == CLIENT + UNTAGGED
    assert rows["other"]["share"] == pytest.approx((CLIENT + UNTAGGED) / TOTAL)


def test_tag_facet_needs_a_tag_dimension(tagged_home, capsys):
    exit_code = CommandOrchestrator().run(
        ["stats", "rollup", "--by", "month", "--tag-facet", "work"]
    )
    captured = capsys.readouterr()

    assert exit_code != 0
    assert "--tag-facet" in captured.err
