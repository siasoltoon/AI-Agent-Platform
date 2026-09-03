import json
from unittest.mock import Mock, patch

from backend.services.ollama_service import OllamaService


def _response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    response.iter_lines.return_value = [json.dumps({**payload, "done": True})]
    return response


def test_agent_action_requests_ollama_json_mode():
    service = OllamaService()
    prompt = 'Return exactly one JSON object per turn: {"action":"tool"}'
    with patch("backend.services.ollama_service.requests.post", return_value=_response({"response": '{"action":"done"}'})) as post:
        result = service.generate(prompt)

    assert result["response"] == '{"action":"done"}'
    payload = post.call_args.kwargs["json"]
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == 0
    assert payload["stream"] is True


def test_agent_action_gets_one_corrective_retry_when_json_is_malformed():
    service = OllamaService()
    prompt = 'Return exactly one JSON object per turn: {"action":"tool"}'
    first = _response({"response": "not json"})
    second = _response({"response": '{"action":"tool","tool":"read_file","args":{}}'})

    with patch("backend.services.ollama_service.requests.post", side_effect=[first, second]) as post:
        result = service.generate(prompt)

    assert result["response"].startswith("{")
    assert post.call_count == 2
    retry_payload = post.call_args_list[1].kwargs["json"]
    assert retry_payload["format"] == "json"
    assert retry_payload["stream"] is True
    assert "not valid JSON" in retry_payload["prompt"]


def test_non_agent_generation_does_not_force_json_mode():
    service = OllamaService()
    with patch("backend.services.ollama_service.requests.post", return_value=_response({"response": "plain text"})) as post:
        result = service.generate("Write a short explanation.")

    assert result["response"] == "plain text"
    payload = post.call_args.kwargs["json"]
    assert "format" not in payload
    assert payload["stream"] is True
