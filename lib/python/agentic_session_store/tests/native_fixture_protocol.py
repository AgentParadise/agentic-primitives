"""Credential-free synthetic wire replies for pinned harness conformance tests."""

import json


def send_events(handler, events):
    body = "".join(
        "event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n"
        for event in events
    ).encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def messages(handler, command=None):
    tool = command is not None
    block = (
        {"type": "tool_use", "id": "fixture-shell", "name": "Bash", "input": {}}
        if tool
        else {"type": "text", "text": ""}
    )
    send_events(
        handler,
        [
            {
                "type": "message_start",
                "message": {
                    "id": "msg_fixture",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-5",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 0},
                },
            },
            {"type": "content_block_start", "index": 0, "content_block": block},
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps({"command": command}),
                }
                if tool
                else {"type": "text_delta", "text": "done"},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": "tool_use" if tool else "end_turn",
                    "stop_sequence": None,
                },
                "usage": {"output_tokens": 1},
            },
            {"type": "message_stop"},
        ],
    )


def responses(handler, command=None):
    item = (
        {
            "type": "function_call",
            "call_id": "fixture-shell",
            "namespace": "functions",
            "name": "exec_command",
            "arguments": json.dumps({"cmd": command}),
        }
        if command
        else {
            "type": "message",
            "id": "msg",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done"}],
        }
    )
    send_events(
        handler,
        [
            {"type": "response.created", "response": {"id": "response"}},
            {"type": "response.output_item.done", "item": item},
            {
                "type": "response.completed",
                "response": {
                    "id": "response",
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                },
            },
        ],
    )
