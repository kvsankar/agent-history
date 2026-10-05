"""Which session a Claude transcript file belongs to, and its parent."""

import json

from agent_history.storage import metrics

PARENT = "11111111-1111-4111-8111-111111111111"
EARLIER = "22222222-2222-4222-8222-222222222222"


def _write_jsonl(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def _line(session_id, uuid, parent_uuid=None, agent_id=None, entry_type="user"):
    entry = {
        "type": entry_type,
        "uuid": uuid,
        "parentUuid": parent_uuid,
        "sessionId": session_id,
        "timestamp": "2026-05-01T04:29:02.000Z",
        "message": {"role": entry_type, "content": "hello"},
    }
    if agent_id:
        entry["agentId"] = agent_id
        entry["isSidechain"] = True
    return entry


def _subagent_lines(session_ids, agent_id="a5b15e31758726051"):
    lines = []
    previous = None
    for index, session_id in enumerate(session_ids):
        uuid = f"m-{index}"
        lines.append(_line(session_id, uuid, previous, agent_id))
        previous = uuid
    return lines


def test_subagent_in_a_subagents_folder_is_its_own_session(tmp_path):
    """The file carries its parent's sessionId; its own ID adds the agentId."""
    session_file = _write_jsonl(
        tmp_path / "project" / PARENT / "subagents" / "agent-a5b15e31758726051.jsonl",
        _subagent_lines([PARENT, PARENT]),
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == f"{PARENT}:a5b15e31758726051"
    assert session_info["parent_session_id"] == PARENT
    assert session_info["is_agent"] is True


def test_workflow_subagent_parent_is_the_session_that_owns_the_folder(tmp_path):
    session_file = _write_jsonl(
        tmp_path / "project" / PARENT / "subagents" / "workflows" / "wf_1" / "agent-a1.jsonl",
        _subagent_lines([PARENT], agent_id="a1"),
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == f"{PARENT}:a1"
    assert session_info["parent_session_id"] == PARENT
    assert session_info["is_agent"] is True


def test_subagent_resumed_in_a_continued_session_belongs_to_the_later_session(tmp_path):
    """A sub-agent resumed after its parent was continued carries both IDs."""
    session_file = _write_jsonl(
        tmp_path / "project" / "agent-a3c4994.jsonl",
        _subagent_lines([EARLIER, PARENT, PARENT], agent_id="a3c4994"),
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == f"{PARENT}:a3c4994"
    assert session_info["parent_session_id"] == PARENT
    assert session_info["is_agent"] is True


def test_subagent_without_agent_id_lines_takes_its_id_from_the_file_name(tmp_path):
    session_file = _write_jsonl(
        tmp_path / "project" / "agent-b7.jsonl",
        [_line(PARENT, "m-0"), _line(PARENT, "m-1", "m-0", entry_type="assistant")],
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == f"{PARENT}:b7"
    assert session_info["parent_session_id"] == PARENT
    assert session_info["is_agent"] is True


def test_continued_main_session_takes_the_id_in_its_file_name(tmp_path):
    """A continued session starts with lines copied from the earlier session."""
    session_file = _write_jsonl(
        tmp_path / "project" / f"{PARENT}.jsonl",
        [
            _line(EARLIER, "m-0"),
            _line(EARLIER, "m-1", "m-0", entry_type="assistant"),
            _line(PARENT, "m-2", "m-1"),
        ],
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == PARENT
    assert session_info["parent_session_id"] is None
    assert session_info["is_agent"] is False


def test_main_session_parent_is_never_a_message_uuid(tmp_path):
    session_file = _write_jsonl(
        tmp_path / "project" / f"{PARENT}.jsonl",
        [_line(PARENT, "m-0"), _line(PARENT, "m-1", "m-0", entry_type="assistant")],
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == PARENT
    assert session_info["parent_session_id"] is None
    assert session_info["is_agent"] is False


def test_main_session_with_an_unrelated_file_name_keeps_its_first_session_id(tmp_path):
    session_file = _write_jsonl(
        tmp_path / "project" / "copy.jsonl",
        [_line(EARLIER, "m-0"), _line(PARENT, "m-1", "m-0")],
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == EARLIER


def test_subagents_with_one_agent_id_under_two_parents_are_two_sessions(tmp_path):
    """Short agent IDs repeat across sessions; the parent keeps them apart."""
    first = _write_jsonl(
        tmp_path / "project" / PARENT / "subagents" / "agent-a1.jsonl",
        _subagent_lines([PARENT], agent_id="a1"),
    )
    second = _write_jsonl(
        tmp_path / "project" / EARLIER / "subagents" / "agent-a1.jsonl",
        _subagent_lines([EARLIER], agent_id="a1"),
    )

    first_info, _messages, _tools = metrics._parse_claude_jsonl(first)
    second_info, _messages, _tools = metrics._parse_claude_jsonl(second)

    assert first_info["session_id"] == f"{PARENT}:a1"
    assert first_info["parent_session_id"] == PARENT
    assert second_info["session_id"] == f"{EARLIER}:a1"
    assert second_info["parent_session_id"] == EARLIER


def test_a_copied_subagent_file_keeps_one_session_id(tmp_path):
    """The same transcript at the project level and in its session folder."""
    lines = _subagent_lines([PARENT], agent_id="a1")
    nested = _write_jsonl(tmp_path / "project" / PARENT / "subagents" / "agent-a1.jsonl", lines)
    legacy = _write_jsonl(tmp_path / "project" / "agent-a1.jsonl", lines)
    assert nested.read_bytes() == legacy.read_bytes()

    nested_info, _messages, _tools = metrics._parse_claude_jsonl(nested)
    legacy_info, _messages, _tools = metrics._parse_claude_jsonl(legacy)

    assert nested_info["session_id"] == legacy_info["session_id"] == f"{PARENT}:a1"
    assert nested_info["parent_session_id"] == legacy_info["parent_session_id"] == PARENT


def test_subagent_without_any_parent_keeps_its_bare_agent_id(tmp_path):
    session_file = _write_jsonl(
        tmp_path / "project" / "agent-c9.jsonl",
        [{"type": "user", "uuid": "m-0", "message": {"role": "user", "content": "hi"}}],
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == "c9"
    assert session_info["parent_session_id"] is None
    assert session_info["is_agent"] is True
