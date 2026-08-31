import pytest

from agent_core.action_parser import ActionParseError, ActionParser


def test_extracts_plain_json_object():
    assert ActionParser.extract_object('{"action":"done","summary":"ok"}') == {
        "action": "done",
        "summary": "ok",
    }


def test_extracts_json_from_markdown_fence():
    result = ActionParser.extract_object('```json\n{"action":"tool","tool":"read_file","args":{"path":"x.txt"}}\n```')
    assert result["tool"] == "read_file"
    assert result["args"]["path"] == "x.txt"


def test_extracts_balanced_object_from_model_prose():
    result = ActionParser.extract_object('I will execute this now: {"action":"tool","tool":"mkdir","args":{"path":"telegram_task_bot"}}')
    assert result["action"] == "tool"
    assert result["tool"] == "mkdir"


def test_rejects_empty_or_invalid_response():
    with pytest.raises(ActionParseError):
        ActionParser.extract_object("")
    with pytest.raises(ActionParseError):
        ActionParser.extract_object("not json at all")


def test_normalizes_tool_aliases():
    result = ActionParser.normalize({"action":"mkdir","args":{"path":"x"}}, {"terminal"}, {"mkdir"})
    assert result["action"] == "tool"
    assert result["tool"] == "mkdir"
