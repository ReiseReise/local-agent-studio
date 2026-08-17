from __future__ import annotations

from local_agent_studio.entities import ModelProfile
from local_agent_studio.services.bootstrap import complete_setup, connector_token
from local_agent_studio.services.prompts import publish_draft


def make_ready(app, *, max_concurrency: int = 3) -> tuple[str, ModelProfile]:
    database = app.state.database
    secret_box = app.state.secret_box
    if connector_token(database, secret_box) is None:
        complete_setup(database, secret_box, "correct horse battery staple")
    with database.session() as session:
        profile = ModelProfile(
            name="Test Chat",
            capability="chat",
            base_url="http://127.0.0.1:9999/v1",
            model_name="test-model",
            api_key_secret=secret_box.protect("test-key"),
            max_concurrency=max_concurrency,
            enabled=True,
            is_active=True,
        )
        session.add(profile)
        publish_draft(session)
    token = connector_token(database, secret_box)
    assert token
    return token, profile
