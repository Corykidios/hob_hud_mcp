"""
hud_vector — full Qdrant surface via operation routing.
Semantic memory layer: store text with metadata, retrieve by similarity.
"""

from __future__ import annotations

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from ..utils import err, get_connections, ok

VECTOR_OPERATIONS = (
    "store              — embed text and store it with optional metadata",
    "find               — retrieve semantically similar entries by natural language query",
    "delete             — delete a stored entry by its ID",
    "list_collections   — list all Qdrant collections",
    "create_collection  — create a new Qdrant collection",
    "delete_collection  — delete a Qdrant collection (destructive)",
    "collection_info    — get details about a collection (count, config)",
)


class HudVectorInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    operation: str = Field(
        ...,
        description=(
            "Qdrant operation to perform. Valid values:\n"
            + "\n".join(f"  {op}" for op in VECTOR_OPERATIONS)
        ),
    )
    collection: str = Field(
        default="",
        description="Collection name. Uses the default configured collection if omitted.",
    )
    text: str = Field(
        default="",
        description="Text to embed and store (for 'store') or to search with (for 'find').",
    )
    metadata: str = Field(
        default="{}",
        description="JSON metadata to attach to a stored entry, e.g. '{\"source\": \"claude\", \"date\": \"2024-01-01\"}'.",
    )
    entry_id: str = Field(
        default="",
        description="Unique string ID for a stored entry. Auto-generated if omitted on store.",
    )
    limit: int = Field(
        default=10,
        description="Maximum number of results to return for 'find'.",
        ge=1,
        le=100,
    )
    score_threshold: float = Field(
        default=0.0,
        description="Minimum similarity score (0.0-1.0) for 'find' results.",
        ge=0.0,
        le=1.0,
    )
    filter: str = Field(
        default="",
        description="JSON Qdrant filter for narrowing 'find' results by metadata fields.",
    )
    vector_size: int = Field(
        default=384,
        description="Embedding vector size for 'create_collection'. Default 384 matches all-MiniLM-L6-v2.",
        ge=1,
    )


async def run_hud_vector(params: HudVectorInput, ctx: Context) -> str:
    import json
    import uuid

    conns = get_connections(ctx)
    if conns.qdrant is None:
        return err(
            "Qdrant is not connected.",
            f"Free the lock (kill stale python processes) and restart. Detail: {conns.qdrant_error}",
        )
    op = params.operation.strip().lower()
    collection = params.collection or conns.qdrant_default_collection

    try:
        if op == "list_collections":
            result = await conns.qdrant.get_collections()
            return ok([c.name for c in result.collections])

        if op == "collection_info":
            info = await conns.qdrant.get_collection(collection)
            return ok({
                "name": collection,
                "vectors_count": info.vectors_count,
                "config": str(info.config),
            })

        if op == "create_collection":
            from qdrant_client.models import Distance, VectorParams
            await conns.qdrant.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=params.vector_size,
                    distance=Distance.COSINE,
                ),
            )
            return ok(f"Collection '{collection}' created with vector size {params.vector_size}.")

        if op == "delete_collection":
            await conns.qdrant.delete_collection(collection)
            return ok(f"Collection '{collection}' deleted.")

        if op == "store":
            if not params.text:
                return err("'text' is required for store")
            from fastembed import TextEmbedding
            embedder = TextEmbedding(model_name=conns.embedding_model)
            vector = list(next(embedder.embed([params.text])))
            metadata = json.loads(params.metadata or "{}")
            entry_id = params.entry_id or str(uuid.uuid4())
            from qdrant_client.models import PointStruct
            await conns.qdrant.upsert(
                collection_name=collection,
                points=[PointStruct(
                    id=_str_to_uuid(entry_id),
                    vector=vector,
                    payload={"text": params.text, **metadata},
                )],
            )
            return ok({"stored": True, "id": entry_id, "collection": collection})

        if op == "find":
            if not params.text:
                return err("'text' is required for find")
            from fastembed import TextEmbedding
            embedder = TextEmbedding(model_name=conns.embedding_model)
            vector = list(next(embedder.embed([params.text])))
            qdrant_filter = None
            if params.filter:
                from qdrant_client.models import Filter
                qdrant_filter = Filter(**json.loads(params.filter))
            results = await conns.qdrant.search(
                collection_name=collection,
                query_vector=vector,
                limit=params.limit,
                score_threshold=params.score_threshold or None,
                query_filter=qdrant_filter,
                with_payload=True,
            )
            return ok([
                {"id": str(r.id), "score": r.score, "payload": r.payload}
                for r in results
            ])

        if op == "delete":
            if not params.entry_id:
                return err("'entry_id' is required for delete")
            from qdrant_client.models import PointIdsList
            await conns.qdrant.delete(
                collection_name=collection,
                points_selector=PointIdsList(points=[_str_to_uuid(params.entry_id)]),
            )
            return ok(f"Entry '{params.entry_id}' deleted from '{collection}'.")

        return err(
            f"Unknown operation: '{op}'",
            "Valid operations: store, find, delete, list_collections, create_collection, delete_collection, collection_info",
        )

    except Exception as e:
        return err(str(e))


def _str_to_uuid(s: str) -> str:
    """Return s as-is if it looks like a UUID, otherwise hash it to one."""
    import hashlib
    try:
        import uuid as _uuid
        _uuid.UUID(s)
        return s
    except ValueError:
        return str(uuid.UUID(hashlib.md5(s.encode()).hexdigest()))