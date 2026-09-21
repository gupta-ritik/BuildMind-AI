"""
Minimal OpenAI-compatible mock server, used ONLY for testing this
codebase's real HTTP/SSE/background-execution behavior without needing
real LLM credentials. Not part of the shipped application.

Returns a fixed sequence of canned responses matching what the Planner,
Explorer, Coder, and Reviewer agents expect, cycling per call.
"""
from __future__ import annotations

import json
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

RESPONSES = [
    json.dumps({
        "goal": "Add subtract fn with test.",
        "steps": ["Add subtract(a, b) to calculator.py", "Add test_subtract"],
        "acceptance_criteria": ["subtract(5,3)==2"],
        "risks": [],
    }),
    json.dumps([
        {"path": "calculator.py", "reason": "main implementation"},
        {"path": "test_calculator.py", "reason": "existing tests"},
    ]),
    json.dumps([
        {
            "path": "calculator.py", "change_type": "modified",
            "full_content": "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
            "explanation": "Added subtract.",
        },
        {
            "path": "test_calculator.py", "change_type": "modified",
            "full_content": "from calculator import add, subtract\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\ndef test_subtract():\n    assert subtract(5, 3) == 2\n",
            "explanation": "Added test.",
        },
    ]),
    json.dumps({"status": "approved", "issues": [], "suggestions": ["Consider type hints."]}),
]

_call_count = 0


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    global _call_count
    body = await request.json()
    content = RESPONSES[_call_count % len(RESPONSES)]
    _call_count += 1
    return JSONResponse({
        "id": "mock-1", "object": "chat.completion", "model": body.get("model", "mock"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    })


if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9999
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
