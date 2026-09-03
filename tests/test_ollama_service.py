import json
import threading
import time
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


def test_cancellation_hard_aborts_blocked_ollama_stream():
    cancel_event = threading.Event()
    service = OllamaService(cancel_event=cancel_event)
    response = Mock()
    response.raise_for_status.return_value = None
    closed = threading.Event()

    def close_response():
        closed.set()

    response.close.side_effect = close_response

    def iter_lines(**_kwargs):
        while not closed.wait(0.01):
            yield None

    response.iter_lines.side_effect = iter_lines

    with patch("backend.services.ollama_service.requests.post", return_value=response):
        thread = threading.Thread(target=lambda: service._generate_once({"model": "qwen2.5-coder:7b", "prompt": "long"}, 30))
        thread.start()
        time.sleep(0.05)
        cancel_event.set()
        thread.join(timeout=1)

    assert not thread.is_alive()
    assert closed.is_set()
    response.close.assert_called()
