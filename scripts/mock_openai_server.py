"""Development-only OpenAI-compatible stub for interface tests.

It never calls a model and must never be used as a production fallback.
"""

from __future__ import annotations

import hashlib

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class ChatPayload(BaseModel):
    messages: list[dict[str, object]]


class EmbeddingPayload(BaseModel):
    input: str | list[str]


@app.post("/v1/chat/completions")
async def chat(payload: ChatPayload):
    question = ""
    for message in reversed(payload.messages):
        if message.get("role") == "user":
            question = str(message.get("content", ""))
            break
    return {
        "id": "mock-chat",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": f"模拟回答：{question[:80]}"},
                "finish_reason": "stop",
            }
        ],
    }


@app.post("/v1/embeddings")
async def embeddings(payload: EmbeddingPayload):
    values = [payload.input] if isinstance(payload.input, str) else payload.input
    rows = []
    for index, value in enumerate(values):
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        vector = [round(byte / 255, 6) for byte in digest[:16]]
        rows.append({"object": "embedding", "index": index, "embedding": vector})
    return {"object": "list", "data": rows}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9999, access_log=False)
