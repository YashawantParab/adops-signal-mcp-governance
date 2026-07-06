from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import KnowledgeChunk

EMBEDDING_DIMENSIONS = 1536


@dataclass(frozen=True)
class RetrievedChunk:
    source: str
    title: str
    content: str
    score: float


def _local_embedding(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def embed_texts(texts: list[str]) -> tuple[list[list[float]], str]:
    settings = get_settings()
    if settings.rag_embedding_provider == "openai" and settings.openai_api_key:
        try:
            client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            response = client.embeddings.create(
                model=settings.rag_embedding_model,
                input=texts,
                dimensions=EMBEDDING_DIMENSIONS,
            )
            return [item.embedding for item in response.data], settings.rag_embedding_model
        except Exception:
            pass
    return [_local_embedding(text) for text in texts], "local-hash-1536"


def _chunks_from_docs() -> list[tuple[str, str, str, int, str]]:
    docs_dir = Path(get_settings().data_dir) / "adops_docs"
    chunks: list[tuple[str, str, str, int, str]] = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        sections = [section.strip() for section in re.split(r"\n(?=##?\s)", text) if section.strip()]
        for index, section in enumerate(sections):
            title_line = section.splitlines()[0].lstrip("# ").strip()
            checksum = hashlib.sha256(f"{path.name}:{index}:{section}".encode("utf-8")).hexdigest()
            chunks.append((path.name, title_line or path.stem, section[:2400], index, checksum))
    return chunks


def index_knowledge_base(db: Session, force: bool = False) -> int:
    chunks = _chunks_from_docs()
    checksums = {chunk[4] for chunk in chunks}
    existing = set(db.execute(select(KnowledgeChunk.checksum)).scalars())
    if not force and checksums and checksums == existing:
        return len(existing)

    db.execute(delete(KnowledgeChunk))
    embeddings, provider = embed_texts([chunk[2] for chunk in chunks])
    for (source, title, content, index, checksum), embedding in zip(chunks, embeddings):
        db.add(
            KnowledgeChunk(
                source=source,
                title=title,
                content=content,
                chunk_index=index,
                embedding=embedding,
                embedding_provider=provider,
                checksum=checksum,
            )
        )
    db.commit()
    return len(chunks)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_norm * right_norm)


def retrieve(db: Session, query: str, limit: int = 4) -> list[RetrievedChunk]:
    if not db.scalar(select(KnowledgeChunk.id).limit(1)):
        index_knowledge_base(db)
    query_vector, _ = embed_texts([query])
    vector = query_vector[0]
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        rows = list(
            db.execute(
                select(KnowledgeChunk)
                .order_by(KnowledgeChunk.embedding.cosine_distance(vector))
                .limit(limit)
            ).scalars()
        )
        return [
            RetrievedChunk(
                source=row.source,
                title=row.title,
                content=row.content,
                score=round(float(_cosine_similarity(vector, list(row.embedding))), 4),
            )
            for row in rows
        ]

    rows = list(db.execute(select(KnowledgeChunk)).scalars())
    scored = sorted(
        ((row, _cosine_similarity(vector, list(row.embedding))) for row in rows),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]
    return [
        RetrievedChunk(source=row.source, title=row.title, content=row.content, score=round(score, 4))
        for row, score in scored
    ]
