from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from pathlib import Path

from docx import Document as DocxDocument
from llama_index.core.node_parser import SentenceSplitter
from pypdf import PdfReader
from sqlalchemy import delete, select, text

from ..database import Database
from ..entities import DocumentChunk, KnowledgeSource, ModelProfile
from ..paths import RuntimePaths
from ..schemas import RetrievedChunk
from .model_client import ModelClient

ALLOWED_EXTENSIONS = {".md": "markdown", ".txt": "text", ".pdf": "pdf", ".docx": "docx"}


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", Path(filename).name)
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Filename is invalid")
    return cleaned[:180]


def extract_text(path: Path) -> tuple[str, str]:
    extension = path.suffix.lower()
    kind = ALLOWED_EXTENSIONS.get(extension)
    if not kind:
        raise ValueError("Unsupported knowledge file type")
    if extension in {".md", ".txt"}:
        raw = path.read_bytes()
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                return kind, raw.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        raise ValueError("Text file encoding is unsupported")
    if extension == ".pdf":
        reader = PdfReader(str(path))
        return kind, "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    document = DocxDocument(str(path))
    return kind, "\n".join(
        paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()
    )


def save_upload(paths: RuntimePaths, source_id: str, filename: str, source_path: Path) -> Path:
    destination = paths.uploads / f"{source_id}-{safe_filename(filename)}"
    shutil.copyfile(source_path, destination)
    return destination


def split_content(content: str) -> list[str]:
    splitter = SentenceSplitter(chunk_size=500, chunk_overlap=80)
    return [chunk.strip() for chunk in splitter.split_text(content) if chunk.strip()]


def _active_embedding_profile(database: Database) -> ModelProfile | None:
    with database.session() as session:
        return session.scalar(
            select(ModelProfile).where(
                ModelProfile.capability == "embedding",
                ModelProfile.enabled.is_(True),
                ModelProfile.is_active.is_(True),
            )
        )


async def reindex_source(database: Database, source_id: str, model_client: ModelClient) -> None:
    try:
        with database.session() as session:
            source = session.get(KnowledgeSource, source_id)
            if not source:
                return
            content = source.content
            expected_hash = source.content_hash
        chunks = split_content(content)
        embedding_profile = _active_embedding_profile(database)
        embeddings: list[list[float] | None] = [None] * len(chunks)
        if embedding_profile and chunks:
            vectors = await model_client.embed(embedding_profile, chunks)
            embeddings = list(vectors)
        with database.session() as session:
            source = session.get(KnowledgeSource, source_id)
            if not source:
                return
            if source.content_hash != expected_hash:
                return
            session.execute(
                text("DELETE FROM document_chunks_fts WHERE source_id = :source_id"), {"source_id": source_id}
            )
            session.execute(delete(DocumentChunk).where(DocumentChunk.source_id == source_id))
            session.flush()
            rows: list[DocumentChunk] = []
            for ordinal, (chunk_text, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
                row = DocumentChunk(
                    source_id=source_id,
                    ordinal=ordinal,
                    text=chunk_text,
                    embedding_json=json.dumps(embedding) if embedding is not None else None,
                )
                session.add(row)
                rows.append(row)
            session.flush()
            for row in rows:
                session.execute(
                    text(
                        "INSERT INTO document_chunks_fts (chunk_id, source_id, text) "
                        "VALUES (:chunk_id, :source_id, :chunk_text)"
                    ),
                    {"chunk_id": row.id, "source_id": source_id, "chunk_text": row.text},
                )
            source.status = "ready"
            source.chunk_count = len(rows)
            source.error_code = None
            session.add(source)
    except Exception as exc:
        with database.session() as session:
            source = session.get(KnowledgeSource, source_id)
            if source:
                source.status = "error"
                source.error_code = type(exc).__name__[:100]
                session.add(source)
        raise


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9_-]+", query):
        if re.fullmatch(r"[\u4e00-\u9fff]+", run):
            if len(run) >= 3:
                terms.extend(run[index : index + 3] for index in range(len(run) - 2))
            elif len(run) == 2:
                terms.append(run)
        elif len(run) >= 2:
            terms.append(run.lower())
    return list(dict.fromkeys(terms))[:24]


async def retrieve(
    database: Database,
    model_client: ModelClient,
    query: str,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    normalized = " ".join(query.split())[:500]
    if not normalized:
        return []
    terms = query_terms(normalized)
    fts_scores: dict[str, float] = {}
    with database.session() as session:
        try:
            rows = session.execute(
                text(
                    "SELECT f.chunk_id, bm25(document_chunks_fts) AS rank "
                    "FROM document_chunks_fts f JOIN knowledge_sources s ON s.id = f.source_id "
                    "WHERE document_chunks_fts MATCH :query AND s.enabled = 1 AND s.status = 'ready' "
                    "ORDER BY rank LIMIT 30"
                ),
                {"query": " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)},
            ).all()
            fts_scores = {row.chunk_id: 1.0 / (1.0 + abs(float(row.rank))) for row in rows}
        except Exception:
            fts_scores = {}
        chunks = session.scalars(
            select(DocumentChunk)
            .join(KnowledgeSource)
            .where(KnowledgeSource.enabled.is_(True), KnowledgeSource.status == "ready")
        ).all()
        source_titles = {
            source.id: source.title
            for source in session.scalars(
                select(KnowledgeSource).where(
                    KnowledgeSource.enabled.is_(True), KnowledgeSource.status == "ready"
                )
            ).all()
        }
    if not fts_scores:
        lowered_terms = [term.lower() for term in terms]
        fts_scores = {
            chunk.id: min(
                0.8,
                0.25 + 0.08 * sum(term in chunk.text.lower() for term in lowered_terms),
            )
            for chunk in chunks
            if any(term in chunk.text.lower() for term in lowered_terms)
        }

    vector_scores: dict[str, float] = {}
    embedding_profile = _active_embedding_profile(database)
    if embedding_profile:
        query_vector = (await model_client.embed(embedding_profile, [normalized]))[0]
        for chunk in chunks:
            if chunk.embedding_json:
                vector_scores[chunk.id] = max(0.0, _cosine(query_vector, json.loads(chunk.embedding_json)))

    scored: list[tuple[float, DocumentChunk]] = []
    for chunk in chunks:
        lexical = fts_scores.get(chunk.id, 0.0)
        semantic = vector_scores.get(chunk.id, 0.0)
        score = (0.55 * lexical + 0.45 * semantic) if vector_scores else lexical
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1].source_id, item[1].ordinal))
    return [
        RetrievedChunk(
            source_id=chunk.source_id,
            source_title=source_titles.get(chunk.source_id, "Knowledge"),
            text=chunk.text[:1200],
            score=round(score, 6),
        )
        for score, chunk in scored[:top_k]
    ]
