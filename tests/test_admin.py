from __future__ import annotations

import json

from sqlalchemy import select

from local_agent_studio.admin.routes import _playground_error
from local_agent_studio.entities import ModelProfile, PromptVersion
from local_agent_studio.services.bootstrap import connector_token
from local_agent_studio.services.prompts import published_prompt

from .conftest import csrf_from


def test_first_setup_login_csrf_and_static(client):
    assert client.get("/admin").url.path == "/admin/setup"
    assert client.get("/admin/static/app.css").status_code == 200
    setup = client.get("/admin/setup")
    rejected = client.post(
        "/admin/setup",
        data={
            "password": "long-enough-password",
            "password_confirm": "different-password",
            "csrf_token": csrf_from(setup),
        },
        follow_redirects=True,
    )
    assert "两次密码不一致" in rejected.text
    assert (
        client.post(
            "/admin/setup",
            data={
                "password": "long-enough-password",
                "password_confirm": "long-enough-password",
                "csrf_token": csrf_from(rejected),
            },
            follow_redirects=False,
        ).status_code
        == 303
    )
    login = client.get("/admin/login")
    assert (
        client.post(
            "/admin/login",
            data={"password": "bad-password", "csrf_token": csrf_from(login)},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        client.post(
            "/admin/login", data={"password": "long-enough-password", "csrf_token": "bad"}
        ).status_code
        == 403
    )


def test_model_prompt_backup_and_export_do_not_export_secrets(admin_client, app):
    page = admin_client.get("/admin/models")
    response = admin_client.post(
        "/admin/models/save",
        data={
            "name": "Primary",
            "capability": "chat",
            "base_url": "https://models.example.test/v1",
            "model_name": "demo-chat",
            "api_key": "highly-sensitive-model-key",
            "temperature": "0.2",
            "max_tokens": "300",
            "timeout_seconds": "20",
            "max_concurrency": "3",
            "csrf_token": csrf_from(page),
        },
        follow_redirects=True,
    )
    assert "模型配置已保存" in response.text
    assert "当前模型" in response.text
    assert ">设为当前</button>" not in response.text
    with app.state.database.session() as session:
        profile = session.scalar(select(ModelProfile).where(ModelProfile.name == "Primary"))
        assert profile is not None
        assert b"highly-sensitive-model-key" not in profile.api_key_secret
        assert profile.enabled is True
        assert profile.is_active is True

    prompts = admin_client.get("/admin/prompts")
    published = admin_client.post(
        "/admin/prompts/publish",
        data={"csrf_token": csrf_from(prompts)},
        follow_redirects=True,
    )
    assert "已发布" in published.text
    with app.state.database.session() as session:
        assert published_prompt(session) is not None
        assert session.scalar(select(PromptVersion).where(PromptVersion.state == "draft")) is not None

    system = admin_client.get("/admin/system")
    admin_client.post(
        "/admin/system/backup",
        data={"csrf_token": csrf_from(system)},
        follow_redirects=True,
    )
    assert list(app.state.paths.backups.glob("studio-*.db"))

    exported = admin_client.get("/admin/system/export")
    payload = json.loads(exported.text)
    assert payload["secrets_included"] is False
    assert "highly-sensitive-model-key" not in exported.text
    assert connector_token(app.state.database, app.state.secret_box) not in exported.text


def test_playground_errors_are_actionable_and_keep_diagnostic_code():
    missing_model = _playground_error("chat_model_not_ready")
    assert "设为当前" in str(missing_model["message"])
    assert missing_model["href"] == "/admin/models"

    bad_key = _playground_error("upstream_http_401")
    assert "API Key" in str(bad_key["message"])
    assert bad_key["code"] == "upstream_http_401"
