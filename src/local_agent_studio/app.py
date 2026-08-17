from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .admin.routes import build_admin_router
from .database import Database
from .entities import KnowledgeSource, ModelProfile
from .logging_config import configure_logging
from .paths import RuntimePaths
from .schemas import ChatCompletionRequest, ChatMessage, InferenceMetadata, ResponsesRequest
from .security import SecretBox, make_secret_box
from .services.bootstrap import (
    agent_enabled,
    connector_token,
    ensure_application_defaults,
    is_setup,
    session_secret,
)
from .services.inference import InferenceError, InferenceService
from .services.model_client import ModelClient
from .services.prompts import ensure_default_prompt, published_prompt
from .settings import LOOPBACK_HOSTS, Settings


def _metadata(request: Request, endpoint: str) -> InferenceMetadata:
    return InferenceMetadata(
        endpoint=endpoint,
        connector_id=request.headers.get("X-Connector-ID"),
        conversation_id=request.headers.get("X-Conversation-ID"),
        message_id=request.headers.get("X-Message-ID"),
        turn_id=request.headers.get("X-Turn-ID"),
    )


def _responses_messages(payload: ResponsesRequest) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    if payload.instructions:
        messages.append(ChatMessage(role="system", content=payload.instructions))
    if isinstance(payload.input, str):
        messages.append(ChatMessage(role="user", content=payload.input))
        return messages
    for item in payload.input:
        if isinstance(item, dict) and item.get("role") in {"user", "assistant", "system", "developer"}:
            content = item.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("type") in {"input_text", "output_text", "text"}
                )
            if isinstance(content, str) and content.strip():
                messages.append(ChatMessage(role=item["role"], content=content))
    if not messages:
        raise HTTPException(status_code=400, detail={"code": "invalid_input"})
    return messages


def create_app(settings: Settings | None = None, secret_box: SecretBox | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    paths = RuntimePaths.create(settings.data_dir)
    database = Database(paths.database)
    database.initialize()
    secret_box = secret_box or make_secret_box(settings.environment)
    ensure_application_defaults(database, secret_box)
    with database.session() as session:
        ensure_default_prompt(session)
    configure_logging(paths.logs, settings.log_max_bytes)
    model_client = ModelClient(secret_box)
    inference = InferenceService(database, model_client, settings.reply_max_chars)

    app = FastAPI(
        title="Local Agent Studio",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.paths = paths
    app.state.database = database
    app.state.secret_box = secret_box
    app.state.model_client = model_client
    app.state.inference = inference
    app.mount(
        "/admin/static",
        StaticFiles(directory=str(Path(__file__).resolve().parent / "admin" / "static")),
        name="admin-static",
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(database, secret_box),
        session_cookie=settings.cookie_name,
        max_age=8 * 60 * 60,
        same_site="strict",
        https_only=settings.secure_cookie,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_security_headers(request: Request, call_next):
        client_host = request.client.host if request.client else ""
        if settings.environment != "test" and client_host not in LOOPBACK_HOSTS:
            return JSONResponse(status_code=403, content={"error": {"code": "loopback_only"}})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    def verify_bearer(authorization: str | None = Header(default=None)) -> None:
        expected = connector_token(database, secret_box)
        if not expected or not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail={"code": "invalid_api_key"})
        import hmac

        if not hmac.compare_digest(authorization[7:], expected):
            raise HTTPException(status_code=401, detail={"code": "invalid_api_key"})

    @app.exception_handler(InferenceError)
    async def inference_error_handler(_request: Request, exc: InferenceError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code}})

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/admin", status_code=302)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "alive", "service": "local-agent-studio"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        checks: dict[str, bool] = {
            "setup": is_setup(database),
            "agent_enabled": agent_enabled(database),
        }
        with database.session() as session:
            session.execute(text("SELECT 1"))
            checks["chat_model"] = (
                session.scalar(
                    select(ModelProfile.id).where(
                        ModelProfile.capability == "chat",
                        ModelProfile.enabled.is_(True),
                        ModelProfile.is_active.is_(True),
                    )
                )
                is not None
            )
            checks["published_prompt"] = published_prompt(session) is not None
            unhealthy_source = session.scalar(
                select(KnowledgeSource.id).where(
                    KnowledgeSource.enabled.is_(True), KnowledgeSource.status != "ready"
                )
            )
            checks["knowledge"] = unhealthy_source is None
        ready = all(checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready", "checks": checks},
        )

    @app.post("/v1/chat/completions", dependencies=[Depends(verify_bearer)])
    async def chat_completions(payload: ChatCompletionRequest, request: Request):
        result = await inference.infer(payload.messages, _metadata(request, "chat.completions"))
        created = int(time.time())
        completion_id = "chatcmpl-" + result.request_id.replace("-", "")
        if payload.stream:

            async def stream() -> AsyncIterator[str]:
                first = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": "local-agent-studio",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": result.text},
                            "finish_reason": None,
                        }
                    ],
                }
                final = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": "local-agent-studio",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                yield "data: " + json.dumps(first, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps(final, ensure_ascii=False) + "\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(stream(), media_type="text/event-stream")
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": "local-agent-studio",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result.text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    @app.post("/v1/responses", dependencies=[Depends(verify_bearer)])
    async def responses(payload: ResponsesRequest, request: Request):
        messages = _responses_messages(payload)
        result = await inference.infer(messages, _metadata(request, "responses"))
        response_id = "resp_" + result.request_id.replace("-", "")
        created = int(time.time())
        response_object = {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": "completed",
            "model": "local-agent-studio",
            "output": [
                {
                    "id": "msg_" + uuid.uuid4().hex,
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": result.text, "annotations": []}],
                }
            ],
            "output_text": result.text,
            "error": None,
        }
        if payload.stream:

            async def response_stream() -> AsyncIterator[str]:
                yield (
                    "event: response.created\ndata: "
                    + json.dumps(
                        {
                            "type": "response.created",
                            "response": {**response_object, "status": "in_progress"},
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                yield (
                    "event: response.output_text.delta\ndata: "
                    + json.dumps(
                        {
                            "type": "response.output_text.delta",
                            "delta": result.text,
                            "output_index": 0,
                            "content_index": 0,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                yield (
                    "event: response.completed\ndata: "
                    + json.dumps(
                        {"type": "response.completed", "response": response_object}, ensure_ascii=False
                    )
                    + "\n\n"
                )

            return StreamingResponse(response_stream(), media_type="text/event-stream")
        return response_object

    app.include_router(build_admin_router())
    return app
