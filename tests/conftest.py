from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from local_agent_studio.app import create_app
from local_agent_studio.security import DevelopmentSecretBox
from local_agent_studio.settings import Settings


@pytest.fixture
def app(tmp_path):
    settings = Settings(environment="test", data_dir=tmp_path)
    return create_app(settings, DevelopmentSecretBox(b"test-secret-material-at-least-24"))


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


def csrf_from(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match, response.text
    return match.group(1)


@pytest.fixture
def admin_client(client):
    response = client.get("/admin/setup")
    assert response.status_code == 200
    response = client.post(
        "/admin/setup",
        data={
            "password": "correct horse battery staple",
            "password_confirm": "correct horse battery staple",
            "csrf_token": csrf_from(response),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    response = client.get("/admin/login")
    response = client.post(
        "/admin/login",
        data={"password": "correct horse battery staple", "csrf_token": csrf_from(response)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "PRIVATE CONTROL PLANE" in response.text
    return client
