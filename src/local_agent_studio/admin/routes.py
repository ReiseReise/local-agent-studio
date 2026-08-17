from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text, update

from .. import __version__
from ..entities import InferenceTrace, KnowledgeSource, ModelProfile, PromptVersion
from ..schemas import ChatMessage, InferenceMetadata
from ..services.bootstrap import (
    agent_enabled,
    authenticate_admin,
    complete_setup,
    connector_token,
    is_setup,
    rotate_connector_token,
    set_agent_enabled,
)
from ..services.inference import InferenceError
from ..services.knowledge import ALLOWED_EXTENSIONS, content_hash, extract_text, reindex_source
from ..services.model_client import UpstreamModelError, validate_base_url
from ..services.prompts import draft_prompt, publish_draft, published_prompt, rollback_to, save_draft

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

PLAYGROUND_ERROR_HELP: dict[str, tuple[str, str | None, str | None]] = {
    "agent_disabled": ("Agent 当前已停用，请先在系统页重新启用。", "/admin/system", "打开系统设置"),
    "chat_model_not_ready": (
        "还没有可用的当前聊天模型。请先启用一个聊天模型并设为当前。",
        "/admin/models",
        "检查模型配置",
    ),
    "prompt_not_published": (
        "还没有已发布的提示词。草稿不会参与回答，请先完成发布。",
        "/admin/prompts",
        "前往发布提示词",
    ),
    "upstream_http_401": (
        "模型接口鉴权失败。请重新填写正确的 API Key，再运行连接测试。",
        "/admin/models",
        "检查 API Key",
    ),
    "upstream_http_402": (
        "模型账户余额不足，请在模型服务商后台检查余额。",
        "/admin/models",
        "检查模型配置",
    ),
    "upstream_http_403": (
        "模型接口拒绝访问，请检查 API Key 权限和账户状态。",
        "/admin/models",
        "检查模型配置",
    ),
    "upstream_http_404": (
        "没有找到模型接口，请检查 Base URL 和模型名称。",
        "/admin/models",
        "检查模型配置",
    ),
    "upstream_http_429": (
        "模型接口当前限流，请稍后再试或检查服务商额度。",
        "/admin/models",
        "检查模型配置",
    ),
    "upstream_timeout": ("模型接口响应超时，请稍后重试。", "/admin/models", "检查模型配置"),
    "upstream_invalid_response": (
        "模型接口返回了无法识别的内容，请检查它是否兼容 OpenAI Chat Completions。",
        "/admin/models",
        "检查模型配置",
    ),
    "empty_response": ("模型返回了空回答，本次没有生成可发送内容。", None, None),
}


def _playground_error(code: str) -> dict[str, str | None]:
    message, href, label = PLAYGROUND_ERROR_HELP.get(
        code,
        ("模型调用失败，本次没有生成回答。", None, None),
    )
    return {"code": code, "message": message, "href": href, "label": label}


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _flash(request: Request, message: str, level: str = "info") -> None:
    request.session["flash"] = {"message": message, "level": level}


def _csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf"] = token
    return token


def _verify_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf", "")
    if not expected or not secrets.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def _context(request: Request, section: str, **extra):
    database = request.app.state.database
    context = {
        "request": request,
        "section": section,
        "csrf_token": _csrf(request),
        "flash": request.session.pop("flash", None),
        "is_setup": is_setup(database),
        "agent_enabled": agent_enabled(database),
    }
    context.update(extra)
    return context


def _guard(request: Request) -> RedirectResponse | None:
    if not is_setup(request.app.state.database):
        return _redirect("/admin/setup")
    if not request.session.get("admin_authenticated"):
        return _redirect("/admin/login")
    return None


def build_admin_router() -> APIRouter:
    router = APIRouter()

    @router.get("/admin/setup", response_class=HTMLResponse)
    async def setup_page(request: Request):
        if is_setup(request.app.state.database):
            return _redirect("/admin/login")
        return templates.TemplateResponse(
            request=request, name="setup.html", context=_context(request, "setup")
        )

    @router.post("/admin/setup")
    async def setup_submit(
        request: Request,
        password: str = Form(...),
        password_confirm: str = Form(...),
        csrf_token: str = Form(...),
    ):
        _verify_csrf(request, csrf_token)
        if password != password_confirm:
            _flash(request, "两次密码不一致。", "error")
            return _redirect("/admin/setup")
        try:
            complete_setup(request.app.state.database, request.app.state.secret_box, password)
        except ValueError as exc:
            _flash(request, str(exc), "error")
            return _redirect("/admin/setup")
        _flash(request, "首次设置完成，请登录。", "success")
        return _redirect("/admin/login")

    @router.get("/admin/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if not is_setup(request.app.state.database):
            return _redirect("/admin/setup")
        return templates.TemplateResponse(
            request=request, name="login.html", context=_context(request, "login")
        )

    @router.post("/admin/login")
    async def login_submit(request: Request, password: str = Form(...), csrf_token: str = Form(...)):
        _verify_csrf(request, csrf_token)
        if not authenticate_admin(request.app.state.database, password):
            _flash(request, "密码不正确。", "error")
            return _redirect("/admin/login")
        request.session.clear()
        request.session["admin_authenticated"] = True
        request.session["csrf"] = secrets.token_urlsafe(24)
        return _redirect("/admin")

    @router.post("/admin/logout")
    async def logout(request: Request, csrf_token: str = Form(...)):
        _verify_csrf(request, csrf_token)
        request.session.clear()
        return _redirect("/admin/login")

    @router.get("/admin", response_class=HTMLResponse)
    async def dashboard(request: Request):
        if guard := _guard(request):
            return guard
        database = request.app.state.database
        with database.session() as session:
            chat_model = session.scalar(
                select(ModelProfile).where(
                    ModelProfile.capability == "chat",
                    ModelProfile.enabled.is_(True),
                    ModelProfile.is_active.is_(True),
                )
            )
            prompt = published_prompt(session)
            source_count = session.scalar(
                select(func.count()).select_from(KnowledgeSource).where(KnowledgeSource.enabled.is_(True))
            )
            ready_count = session.scalar(
                select(func.count()).select_from(KnowledgeSource).where(KnowledgeSource.status == "ready")
            )
            traces = session.scalars(
                select(InferenceTrace).order_by(InferenceTrace.created_at.desc()).limit(8)
            ).all()
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context=_context(
                request,
                "dashboard",
                chat_model=chat_model,
                prompt=prompt,
                source_count=source_count or 0,
                ready_count=ready_count or 0,
                traces=traces,
            ),
        )

    @router.get("/admin/models", response_class=HTMLResponse)
    async def models_page(request: Request, edit: str | None = None):
        if guard := _guard(request):
            return guard
        with request.app.state.database.session() as session:
            models = session.scalars(
                select(ModelProfile).order_by(ModelProfile.capability, ModelProfile.name)
            ).all()
            editing = session.get(ModelProfile, edit) if edit else None
        return templates.TemplateResponse(
            request=request,
            name="models.html",
            context=_context(request, "models", models=models, editing=editing),
        )

    @router.post("/admin/models/save")
    async def model_save(
        request: Request,
        name: str = Form(...),
        capability: str = Form(...),
        base_url: str = Form(...),
        model_name: str = Form(...),
        api_key: str = Form(""),
        temperature: float = Form(0.3),
        max_tokens: int = Form(300),
        timeout_seconds: int = Form(20),
        max_concurrency: int = Form(3),
        profile_id: str = Form(""),
        csrf_token: str = Form(...),
    ):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        if capability not in {"chat", "embedding"}:
            raise HTTPException(status_code=400, detail="Invalid capability")
        try:
            normalized_url = validate_base_url(base_url)
            if not (
                0 <= temperature <= 2
                and 1 <= max_tokens <= 8000
                and 2 <= timeout_seconds <= 120
                and 1 <= max_concurrency <= 10
            ):
                raise ValueError("模型参数超出允许范围")
            with request.app.state.database.session() as session:
                profile = session.get(ModelProfile, profile_id) if profile_id else None
                if not profile:
                    if (
                        not api_key
                        and "localhost" not in normalized_url
                        and "127.0.0.1" not in normalized_url
                    ):
                        raise ValueError("云端模型必须填写 API Key")
                    profile = ModelProfile(
                        name=name.strip(),
                        capability=capability,
                        base_url=normalized_url,
                        model_name=model_name.strip(),
                        api_key_secret=request.app.state.secret_box.protect(api_key),
                    )
                else:
                    profile.name = name.strip()
                    profile.capability = capability
                    profile.base_url = normalized_url
                    profile.model_name = model_name.strip()
                    if api_key:
                        profile.api_key_secret = request.app.state.secret_box.protect(api_key)
                profile.temperature = temperature
                profile.max_tokens = max_tokens
                profile.timeout_seconds = timeout_seconds
                profile.max_concurrency = max_concurrency
                profile.enabled = True
                session.add(profile)
                session.flush()
                active_id = session.scalar(
                    select(ModelProfile.id).where(
                        ModelProfile.capability == capability,
                        ModelProfile.enabled.is_(True),
                        ModelProfile.is_active.is_(True),
                    )
                )
                if active_id is None:
                    profile.is_active = True
                    session.add(profile)
            _flash(request, "模型配置已保存；若这是首个同类模型，已自动设为当前。", "success")
        except Exception as exc:
            _flash(request, f"保存失败：{type(exc).__name__}", "error")
        return _redirect("/admin/models")

    @router.post("/admin/models/{profile_id}/activate")
    async def model_activate(request: Request, profile_id: str, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        with request.app.state.database.session() as session:
            profile = session.get(ModelProfile, profile_id)
            if not profile:
                raise HTTPException(status_code=404)
            session.execute(
                update(ModelProfile)
                .where(ModelProfile.capability == profile.capability)
                .values(is_active=False)
            )
            profile.enabled = True
            profile.is_active = True
            session.add(profile)
        _flash(request, "当前模型已切换。", "success")
        return _redirect("/admin/models")

    @router.post("/admin/models/{profile_id}/toggle")
    async def model_toggle(request: Request, profile_id: str, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        with request.app.state.database.session() as session:
            profile = session.get(ModelProfile, profile_id)
            if not profile:
                raise HTTPException(status_code=404)
            profile.enabled = not profile.enabled
            if not profile.enabled:
                profile.is_active = False
            session.add(profile)
        return _redirect("/admin/models")

    @router.post("/admin/models/{profile_id}/test")
    async def model_test(request: Request, profile_id: str, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        with request.app.state.database.session() as session:
            profile = session.get(ModelProfile, profile_id)
        if not profile:
            raise HTTPException(status_code=404)
        try:
            result = await request.app.state.model_client.test(profile)
            _flash(request, result, "success")
        except UpstreamModelError as exc:
            _flash(request, f"连接失败：{exc.code}", "error")
        return _redirect("/admin/models")

    @router.get("/admin/prompts", response_class=HTMLResponse)
    async def prompts_page(request: Request):
        if guard := _guard(request):
            return guard
        with request.app.state.database.session() as session:
            draft = draft_prompt(session)
            published = published_prompt(session)
            versions = session.scalars(
                select(PromptVersion).order_by(PromptVersion.version_number.desc()).limit(30)
            ).all()
        return templates.TemplateResponse(
            request=request,
            name="prompts.html",
            context=_context(request, "prompts", draft=draft, published=published, versions=versions),
        )

    @router.post("/admin/prompts/draft")
    async def prompt_save(
        request: Request, content: str = Form(...), change_note: str = Form(""), csrf_token: str = Form(...)
    ):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        try:
            with request.app.state.database.session() as session:
                save_draft(session, content, change_note)
            _flash(request, "草稿已保存，线上版本未改变。", "success")
        except ValueError as exc:
            _flash(request, str(exc), "error")
        return _redirect("/admin/prompts")

    @router.post("/admin/prompts/publish")
    async def prompt_publish(request: Request, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        try:
            with request.app.state.database.session() as session:
                published = publish_draft(session)
            _flash(request, f"提示词 v{published.version_number} 已发布。", "success")
        except ValueError as exc:
            _flash(request, str(exc), "error")
        return _redirect("/admin/prompts")

    @router.post("/admin/prompts/test", response_class=HTMLResponse)
    async def prompt_test(request: Request, question: str = Form(...), csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        with request.app.state.database.session() as session:
            draft = draft_prompt(session)
            published = published_prompt(session)
            versions = session.scalars(
                select(PromptVersion).order_by(PromptVersion.version_number.desc()).limit(30)
            ).all()
        result = None
        error = None
        if not draft:
            error = "prompt_draft_missing"
        else:
            try:
                result = await request.app.state.inference.infer(
                    [ChatMessage(role="user", content=question)],
                    InferenceMetadata(endpoint="admin.prompt_test", connector_id="local-admin"),
                    prompt_override=draft,
                )
            except InferenceError as exc:
                error = exc.code
        return templates.TemplateResponse(
            request=request,
            name="prompts.html",
            context=_context(
                request,
                "prompts",
                draft=draft,
                published=published,
                versions=versions,
                prompt_test_result=result,
                prompt_test_error=error,
                prompt_test_question=question,
            ),
        )

    @router.post("/admin/prompts/{version_id}/rollback")
    async def prompt_rollback(request: Request, version_id: str, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        with request.app.state.database.session() as session:
            published = rollback_to(session, version_id)
        _flash(request, f"已回滚并发布为 v{published.version_number}。", "success")
        return _redirect("/admin/prompts")

    @router.get("/admin/knowledge", response_class=HTMLResponse)
    async def knowledge_page(request: Request, edit: str | None = None):
        if guard := _guard(request):
            return guard
        with request.app.state.database.session() as session:
            sources = session.scalars(
                select(KnowledgeSource).order_by(KnowledgeSource.updated_at.desc())
            ).all()
            editing = session.get(KnowledgeSource, edit) if edit else None
        return templates.TemplateResponse(
            request=request,
            name="knowledge.html",
            context=_context(request, "knowledge", sources=sources, editing=editing),
        )

    @router.post("/admin/knowledge/text")
    async def knowledge_text(
        request: Request,
        background_tasks: BackgroundTasks,
        title: str = Form(...),
        content: str = Form(...),
        source_id: str = Form(""),
        csrf_token: str = Form(...),
    ):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        normalized = content.strip()
        if len(normalized) < 10:
            _flash(request, "知识内容至少需要10个字符。", "error")
            return _redirect("/admin/knowledge")
        with request.app.state.database.session() as session:
            source = session.get(KnowledgeSource, source_id) if source_id else None
            if source:
                source.title = title.strip()[:200]
                if source.content_hash != content_hash(normalized):
                    source.content = normalized
                    source.content_hash = content_hash(normalized)
                    source.version += 1
                    source.status = "pending"
                session.add(source)
            else:
                source = KnowledgeSource(
                    title=title.strip()[:200],
                    kind="text",
                    content=normalized,
                    content_hash=content_hash(normalized),
                    status="pending",
                )
                session.add(source)
                session.flush()
            source_id = source.id
        background_tasks.add_task(
            reindex_source, request.app.state.database, source_id, request.app.state.model_client
        )
        _flash(request, "知识已保存，正在重建索引。", "success")
        return _redirect("/admin/knowledge")

    @router.post("/admin/knowledge/upload")
    async def knowledge_upload(
        request: Request,
        background_tasks: BackgroundTasks,
        title: str = Form(""),
        upload: UploadFile = File(...),
        csrf_token: str = Form(...),
    ):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        filename = upload.filename or ""
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            _flash(request, "只支持 MD、TXT、PDF、DOCX。", "error")
            return _redirect("/admin/knowledge")
        body = await upload.read(request.app.state.settings.max_upload_bytes + 1)
        if len(body) > request.app.state.settings.max_upload_bytes:
            _flash(request, "文件超过20MB限制。", "error")
            return _redirect("/admin/knowledge")
        source = KnowledgeSource(
            title=(title.strip() or Path(filename).stem)[:200],
            kind=ALLOWED_EXTENSIONS[extension],
            original_filename=Path(filename).name[:255],
            content="pending",
            content_hash="",
            status="pending",
        )
        stored: Path | None = None
        try:
            with request.app.state.database.session() as session:
                session.add(source)
                session.flush()
                stored = request.app.state.paths.uploads / f"{source.id}{extension}"
                stored.write_bytes(body)
                kind, extracted = extract_text(stored)
                if len(extracted) < 10:
                    raise ValueError("文件中没有足够的可用文字")
                source.kind = kind
                source.stored_path = str(stored)
                source.content = extracted
                source.content_hash = content_hash(extracted)
                session.add(source)
                source_id = source.id
        except Exception as exc:
            if stored:
                stored.unlink(missing_ok=True)
            _flash(request, f"导入失败：{type(exc).__name__}", "error")
            return _redirect("/admin/knowledge")
        background_tasks.add_task(
            reindex_source, request.app.state.database, source_id, request.app.state.model_client
        )
        _flash(request, "文件已导入，正在建立索引。", "success")
        return _redirect("/admin/knowledge")

    @router.post("/admin/knowledge/{source_id}/toggle")
    async def knowledge_toggle(request: Request, source_id: str, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        with request.app.state.database.session() as session:
            source = session.get(KnowledgeSource, source_id)
            if not source:
                raise HTTPException(status_code=404)
            source.enabled = not source.enabled
            session.add(source)
        return _redirect("/admin/knowledge")

    @router.post("/admin/knowledge/{source_id}/reindex")
    async def knowledge_reindex(
        request: Request, background_tasks: BackgroundTasks, source_id: str, csrf_token: str = Form(...)
    ):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        with request.app.state.database.session() as session:
            source = session.get(KnowledgeSource, source_id)
            if not source:
                raise HTTPException(status_code=404)
            source.status = "pending"
            session.add(source)
        background_tasks.add_task(
            reindex_source, request.app.state.database, source_id, request.app.state.model_client
        )
        return _redirect("/admin/knowledge")

    @router.post("/admin/knowledge/{source_id}/delete")
    async def knowledge_delete(request: Request, source_id: str, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        stored_path: str | None = None
        with request.app.state.database.session() as session:
            source = session.get(KnowledgeSource, source_id)
            if not source:
                raise HTTPException(status_code=404)
            session.execute(
                text("DELETE FROM document_chunks_fts WHERE source_id = :source_id"), {"source_id": source_id}
            )
            stored_path = source.stored_path
            session.delete(source)
        if stored_path:
            try:
                Path(stored_path).unlink(missing_ok=True)
            except OSError:
                _flash(request, "知识已退出检索，但原始上传文件需要人工检查。", "error")
                return _redirect("/admin/knowledge")
        _flash(request, "知识源已删除并退出检索。", "success")
        return _redirect("/admin/knowledge")

    @router.get("/admin/playground", response_class=HTMLResponse)
    async def playground_page(request: Request):
        if guard := _guard(request):
            return guard
        return templates.TemplateResponse(
            request=request,
            name="playground.html",
            context=_context(request, "playground", result=None, question=""),
        )

    @router.post("/admin/playground", response_class=HTMLResponse)
    async def playground_run(request: Request, question: str = Form(...), csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        result = None
        error = None
        try:
            result = await request.app.state.inference.infer(
                [ChatMessage(role="user", content=question)],
                InferenceMetadata(endpoint="admin.playground", connector_id="local-admin"),
            )
        except InferenceError as exc:
            error = _playground_error(exc.code)
        return templates.TemplateResponse(
            request=request,
            name="playground.html",
            context=_context(request, "playground", result=result, question=question, error=error),
        )

    @router.get("/admin/integration", response_class=HTMLResponse)
    async def integration_page(request: Request):
        if guard := _guard(request):
            return guard
        token = connector_token(request.app.state.database, request.app.state.secret_box)
        return templates.TemplateResponse(
            request=request,
            name="integration.html",
            context=_context(request, "integration", connector_token=token),
        )

    @router.post("/admin/integration/rotate")
    async def integration_rotate(request: Request, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        rotate_connector_token(request.app.state.database, request.app.state.secret_box)
        _flash(request, "接入 Token 已轮换；旧 Token 立即失效。", "success")
        return _redirect("/admin/integration")

    @router.get("/admin/system", response_class=HTMLResponse)
    async def system_page(request: Request):
        if guard := _guard(request):
            return guard
        return templates.TemplateResponse(
            request=request,
            name="system.html",
            context=_context(
                request, "system", paths=request.app.state.paths, settings=request.app.state.settings
            ),
        )

    @router.post("/admin/system/toggle-agent")
    async def system_toggle(request: Request, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        set_agent_enabled(request.app.state.database, not agent_enabled(request.app.state.database))
        return _redirect("/admin/system")

    @router.get("/admin/system/export")
    async def system_export(request: Request):
        if guard := _guard(request):
            return guard
        with request.app.state.database.session() as session:
            models = session.scalars(select(ModelProfile).order_by(ModelProfile.name)).all()
            prompts = session.scalars(select(PromptVersion).order_by(PromptVersion.version_number)).all()
            sources = session.scalars(select(KnowledgeSource).order_by(KnowledgeSource.created_at)).all()
        payload = {
            "format": "local-agent-studio-export-v1",
            "created_at": datetime.now(UTC).isoformat(),
            "version": __version__,
            "secrets_included": False,
            "models": [
                {
                    "name": item.name,
                    "capability": item.capability,
                    "base_url": item.base_url,
                    "model_name": item.model_name,
                    "temperature": item.temperature,
                    "max_tokens": item.max_tokens,
                    "timeout_seconds": item.timeout_seconds,
                    "max_concurrency": item.max_concurrency,
                    "enabled": item.enabled,
                    "is_active": item.is_active,
                }
                for item in models
            ],
            "prompts": [
                {
                    "version": item.version_number,
                    "state": item.state,
                    "content": item.content,
                    "change_note": item.change_note,
                }
                for item in prompts
            ],
            "knowledge": [
                {
                    "title": item.title,
                    "kind": item.kind,
                    "content": item.content,
                    "enabled": item.enabled,
                    "version": item.version,
                }
                for item in sources
            ],
        }
        filename = f"local-agent-studio-export-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/admin/system/backup")
    async def system_backup(request: Request, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        destination = request.app.state.paths.backups / f"studio-{datetime.now(UTC):%Y%m%d-%H%M%S}.db"
        request.app.state.database.backup(destination)
        _flash(request, f"本地备份已完成：{destination.name}", "success")
        return _redirect("/admin/system")

    @router.post("/admin/system/diagnose")
    async def system_diagnose(request: Request, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        with request.app.state.database.session() as session:
            session.execute(text("SELECT 1"))
            model_count = session.scalar(select(func.count()).select_from(ModelProfile)) or 0
            source_errors = (
                session.scalar(
                    select(func.count()).select_from(KnowledgeSource).where(KnowledgeSource.status == "error")
                )
                or 0
            )
        _flash(
            request,
            f"诊断完成：数据库正常，模型 {model_count} 个，知识错误 {source_errors} 个。",
            "success" if source_errors == 0 else "error",
        )
        return _redirect("/admin/system")

    @router.post("/admin/system/check-update")
    async def system_check_update(request: Request, csrf_token: str = Form(...)):
        if guard := _guard(request):
            return guard
        _verify_csrf(request, csrf_token)
        try:
            async with httpx.AsyncClient(
                timeout=5,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(
                    "https://api.github.com/repos/ReiseReise/local-agent-studio/releases/latest",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "local-agent-studio"},
                )
            if response.status_code == 404:
                message = f"当前版本 {__version__}；尚无公开 Release。"
            else:
                response.raise_for_status()
                latest = str(response.json().get("tag_name", "unknown"))[:50]
                message = f"当前版本 {__version__}；最新公开版本 {latest}。"
            _flash(request, message, "success")
        except (httpx.HTTPError, ImportError, ValueError, TypeError):
            _flash(request, "更新检查失败；未改变任何本机配置。", "error")
        return _redirect("/admin/system")

    return router
