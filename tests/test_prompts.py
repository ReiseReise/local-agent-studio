from __future__ import annotations

from local_agent_studio.entities import PromptVersion
from local_agent_studio.services.prompts import (
    draft_prompt,
    publish_draft,
    published_prompt,
    rollback_to,
    save_draft,
)


def test_draft_publish_and_rollback_are_versioned(app):
    database = app.state.database
    with database.session() as session:
        initial = draft_prompt(session)
        assert initial and initial.state == "draft"
        save_draft(session, "A custom persona that is deliberately longer than twenty characters.", "first")
        first = publish_draft(session)
        first_id = first.id
        assert first.state == "published"

    with database.session() as session:
        save_draft(
            session, "A second persona that is also deliberately longer than twenty characters.", "second"
        )
        second = publish_draft(session)
        assert second.version_number > first.version_number
        rolled_back = rollback_to(session, first_id)
        assert rolled_back.content.startswith("A custom persona")
        assert rolled_back.version_number > second.version_number

    with database.session() as session:
        current = published_prompt(session)
        assert current and current.id == rolled_back.id
        versions = session.query(PromptVersion).all()
        assert len({item.version_number for item in versions}) == len(versions)
