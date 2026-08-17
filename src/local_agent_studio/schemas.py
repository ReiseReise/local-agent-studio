from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message content must not be empty")
        if len(value) > 100_000:
            raise ValueError("message content is too large")
        return value


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "local-agent-studio"
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "local-agent-studio"
    input: str | list[Any]
    instructions: str | None = None
    stream: bool = False

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str | list[Any]) -> str | list[Any]:
        if isinstance(value, str):
            if not value.strip() or len(value) > 100_000:
                raise ValueError("response input must contain between 1 and 100000 characters")
            return value
        if not value or len(value) > 200:
            raise ValueError("response input must contain between 1 and 200 items")
        return value

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 100_000:
            raise ValueError("instructions are too large")
        return value


class InferenceMetadata(BaseModel):
    endpoint: str
    connector_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    turn_id: str | None = None


class RetrievedChunk(BaseModel):
    source_id: str
    source_title: str
    text: str
    score: float


class InferenceResult(BaseModel):
    request_id: str
    text: str
    model_name: str
    prompt_version: int
    duration_ms: int
    retrieved: list[RetrievedChunk]
