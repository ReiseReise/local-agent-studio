from __future__ import annotations

import pytest

from local_agent_studio.entities import KnowledgeSource
from local_agent_studio.services.knowledge import content_hash, reindex_source, retrieve


@pytest.mark.asyncio
async def test_edit_disable_and_delete_immediately_leave_retrieval(app):
    database = app.state.database
    with database.session() as session:
        source = KnowledgeSource(
            title="Product facts",
            kind="text",
            content="青石杯的标准容量是三百毫升，仅提供雾灰色。",
            content_hash=content_hash("青石杯的标准容量是三百毫升，仅提供雾灰色。"),
            status="pending",
        )
        session.add(source)
        session.flush()
        source_id = source.id
    await reindex_source(database, source_id, app.state.model_client)
    assert await retrieve(database, app.state.model_client, "青石杯")

    replacement = "青石杯已经停产，替代款是云纹杯。"
    with database.session() as session:
        source = session.get(KnowledgeSource, source_id)
        source.content = replacement
        source.content_hash = content_hash(replacement)
        source.status = "pending"
        source.version += 1
    await reindex_source(database, source_id, app.state.model_client)
    old = await retrieve(database, app.state.model_client, "三百毫升")
    assert not old
    assert await retrieve(database, app.state.model_client, "云纹杯")
    assert await retrieve(database, app.state.model_client, "云纹杯容量是多少？")

    with database.session() as session:
        source = session.get(KnowledgeSource, source_id)
        source.enabled = False
    assert not await retrieve(database, app.state.model_client, "云纹杯")

    with database.session() as session:
        source = session.get(KnowledgeSource, source_id)
        session.delete(source)
    assert not await retrieve(database, app.state.model_client, "云纹杯")


@pytest.mark.asyncio
async def test_stale_reindex_cannot_overwrite_new_content(app, monkeypatch):
    database = app.state.database
    original = "旧内容有足够长度用于建立知识索引。"
    with database.session() as session:
        source = KnowledgeSource(
            title="Race",
            kind="text",
            content=original,
            content_hash=content_hash(original),
            status="pending",
        )
        session.add(source)
        session.flush()
        source_id = source.id

    import local_agent_studio.services.knowledge as module

    real_split = module.split_content

    def changing_split(content: str):
        replacement = "新内容会在旧索引落库之前生效。"
        with database.session() as session:
            source = session.get(KnowledgeSource, source_id)
            source.content = replacement
            source.content_hash = content_hash(replacement)
            source.status = "pending"
        return real_split(content)

    monkeypatch.setattr(module, "split_content", changing_split)
    await reindex_source(database, source_id, app.state.model_client)
    with database.session() as session:
        source = session.get(KnowledgeSource, source_id)
        assert source.status == "pending"
        assert source.chunk_count == 0
