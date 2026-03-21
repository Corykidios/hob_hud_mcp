"""
hob_hud_mcp — Corpus Intelligence MCP Server
Three databases, ten tools, one purpose: make sense of vast corpora.

Raw layer  (full DB access):  hud_mongo · hud_graph · hud_vector
Pipeline   (research workflows): hud_ingest · hud_search · hud_extract
                                  hud_relate · hud_order · hud_annotate · hud_report
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .connections import lifespan
from .tools.raw_mongo import HudMongoInput, run_hud_mongo
from .tools.raw_graph import HudGraphInput, run_hud_graph
from .tools.raw_vector import HudVectorInput, run_hud_vector
from .tools.pipeline_ingest import HudIngestInput, run_hud_ingest
from .tools.pipeline_tools import (
    HudSearchInput, run_hud_search,
    HudExtractInput, run_hud_extract,
    HudRelateInput, run_hud_relate,
    HudOrderInput, run_hud_order,
    HudAnnotateInput, run_hud_annotate,
    HudReportInput, run_hud_report,
)

mcp = FastMCP("hob_hud_mcp", lifespan=lifespan)


# ── Raw database tools ─────────────────────────────────────────────

@mcp.tool(
    name="hud_mongo",
    annotations={
        "title": "MongoDB Raw Access",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def hud_mongo(params: HudMongoInput, ctx=None) -> str:
    """
    Full MongoDB access via operation routing.

    Covers all document CRUD operations, aggregation pipelines, text search,
    schema inference, index management, collection and database management.
    Use this for direct, low-level interaction with the corpus store.

    Args:
        params (HudMongoInput): Operation and its parameters.

    Returns:
        str: JSON result with 'status' and 'result' or 'message' fields.
    """
    return await run_hud_mongo(params, ctx)


@mcp.tool(
    name="hud_graph",
    annotations={
        "title": "Neo4j Graph Raw Access",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def hud_graph(params: HudGraphInput, ctx=None) -> str:
    """
    Full Neo4j access via operation routing.

    Execute arbitrary Cypher queries (read or write), introspect the graph
    schema, and list GDS procedures. Use this for custom graph patterns
    beyond what hud_relate provides.

    Args:
        params (HudGraphInput): Operation and Cypher query.

    Returns:
        str: JSON result with query records or operation counters.
    """
    return await run_hud_graph(params, ctx)


@mcp.tool(
    name="hud_vector",
    annotations={
        "title": "Qdrant Vector Raw Access",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def hud_vector(params: HudVectorInput, ctx=None) -> str:
    """
    Full Qdrant vector database access via operation routing.

    Store text with metadata (auto-embeds locally), retrieve by semantic
    similarity, manage collections. Use this for direct semantic memory
    operations beyond what hud_search provides.

    Args:
        params (HudVectorInput): Operation, text, and optional metadata.

    Returns:
        str: JSON result with stored IDs, similarity hits, or collection info.
    """
    return await run_hud_vector(params, ctx)


# ── Pipeline tools ────────────────────────────────────────────────

@mcp.tool(
    name="hud_ingest",
    annotations={
        "title": "Corpus Ingestion",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def hud_ingest(params: HudIngestInput, ctx=None) -> str:
    """
    Load documents from files and directories into the corpus.

    Auto-detects format (plain text, JSON conversation exports, Markdown,
    JSONL, CSV). Handles ChatGPT exports, Claude exports, Obsidian vaults,
    and arbitrary text files. Skips already-ingested files by default.

    Args:
        params (HudIngestInput): Path, source label, and ingest options.

    Returns:
        str: JSON summary of ingested document counts and source labels.
    """
    return await run_hud_ingest(params, ctx)


@mcp.tool(
    name="hud_search",
    annotations={
        "title": "Corpus Search",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def hud_search(params: HudSearchInput, ctx=None) -> str:
    """
    Retrieve documents from the corpus using keyword, semantic, or hybrid search.

    Keyword search uses MongoDB full-text indexes.
    Semantic search uses Qdrant vector similarity (fastembed, local).
    Hybrid search combines both. Also supports filtering by source or date,
    and fetching surrounding context for a document.

    Args:
        params (HudSearchInput): Query, operation type, and filters.

    Returns:
        str: JSON list of matching documents with scores where applicable.
    """
    return await run_hud_search(params, ctx)


@mcp.tool(
    name="hud_extract",
    annotations={
        "title": "Entity and Term Extraction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def hud_extract(params: HudExtractInput, ctx=None) -> str:
    """
    Extract named entities and terms from corpus documents.

    Identifies and catalogues named things — people, places, concepts, works —
    from text. Stores extracted terms with occurrence references for later
    retrieval. Supports merging aliases and filtering by type.

    Args:
        params (HudExtractInput): Source document or text and extraction options.

    Returns:
        str: JSON list of extracted entities or term lookup results.
    """
    return await run_hud_extract(params, ctx)


@mcp.tool(
    name="hud_relate",
    annotations={
        "title": "Graph Relationship Management",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def hud_relate(params: HudRelateInput, ctx=None) -> str:
    """
    Create and query relationships between entities in the Neo4j graph.

    Build a knowledge graph of how entities connect: who appears with whom,
    what concepts are linked, how terms relate across sources. Supports
    path finding, neighborhood traversal, and custom graph patterns.

    Args:
        params (HudRelateInput): Entities, relationship type, and graph query options.

    Returns:
        str: JSON graph query results or confirmation of created relationships.
    """
    return await run_hud_relate(params, ctx)


@mcp.tool(
    name="hud_order",
    annotations={
        "title": "Temporal Ordering",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def hud_order(params: HudOrderInput, ctx=None) -> str:
    """
    Assign and query temporal metadata on corpus documents.

    Maintains two independent date fields per document:
    - created_date: when the document was written or published
    - referenced_period: the historical era the document discusses

    This distinction is essential for academic work where a modern paper
    discusses ancient events. Query by either field independently.

    Args:
        params (HudOrderInput): Document ID, date values, and query ranges.

    Returns:
        str: JSON document list sorted chronologically or confirmation of date assignment.
    """
    return await run_hud_order(params, ctx)


@mcp.tool(
    name="hud_annotate",
    annotations={
        "title": "Annotation and Named Collections",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def hud_annotate(params: HudAnnotateInput, ctx=None) -> str:
    """
    Tag documents, add notes, and curate named collections.

    The human-in-the-loop layer: attach free-text notes, apply tags,
    and organise documents into named collections for export or further
    processing. Named collections are the primary output containers
    (e.g. an exemplar set, a bibliography, a thematic cluster).

    Args:
        params (HudAnnotateInput): Document ID, annotation content, and collection name.

    Returns:
        str: JSON confirmation or collection contents.
    """
    return await run_hud_annotate(params, ctx)


@mcp.tool(
    name="hud_report",
    annotations={
        "title": "Corpus Reports and Export",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def hud_report(params: HudReportInput, ctx=None) -> str:
    """
    Generate statistics, summaries, comparisons, and exports from the corpus.

    Provides high-level overviews of ingested data, side-by-side source
    comparisons, and formatted document exports in JSON or Markdown.
    Use this to understand the current state of the corpus and produce
    shareable outputs from accumulated research.

    Args:
        params (HudReportInput): Report type and output format options.

    Returns:
        str: JSON or Markdown report content.
    """
    return await run_hud_report(params, ctx)


# ── Entry point ──────────────────────────────────────────────────

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()