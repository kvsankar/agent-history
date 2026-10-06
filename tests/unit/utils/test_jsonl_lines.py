"""Reading transcript lines with large binary reads gives the same lines as text mode."""

from agent_history.utils.jsonl import iter_jsonl_lines


def test_lines_match_text_mode_reading(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_bytes(
        "﻿".encode()
        + b'{"a": "caf\xc3\xa9"}\r\n'
        + b'{"b": "\xe2\x80\xa8 inside"}\n'
        + b"\n"
        + b'{"c": 3}'
    )

    with open(path, encoding="utf-8-sig") as handle:
        expected = [line.strip() for line in handle]

    assert [line.strip() for line in iter_jsonl_lines(path)] == expected


def test_large_file_lines_are_complete(tmp_path):
    path = tmp_path / "big.jsonl"
    lines = [f'{{"n": {n}, "pad": "{"x" * 5000}"}}' for n in range(3000)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert [line.rstrip("\n") for line in iter_jsonl_lines(path)] == lines
