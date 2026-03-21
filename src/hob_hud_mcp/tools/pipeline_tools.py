"""
Pipeline tools: hud_search, hud_extract, hud_relate, hud_order, hud_annotate, hud_report.
Each is a single Letta-style operation-routed tool.
"""

from __future__ import annotations

import json
from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from ..utils import err, get_connections, ok


# ============================================================================
# hud_search
# ============================================================================

SEARCH_OPERATIONS = (
    "keyword    — MongoDB text search across the corpus",
    "semantic   — Qdrant vector similarity search",
    "hybrid     — keyword + semantic combined, results merged and ranked",
    "by_source  — filter corpus documents by source label",
    "by_date    — filter corpus documents by date range",
    "context    — fetch surrounding documents for a given document ID",
)


class HudSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    operation: str = Field(..., description="Search operation. Valid values:\n" + "\n".join(f"  {o}" for o in SEARCH_OPERATIONS))
    query: str = Field(default="", description="Search query string.")
    collection: str = Field(default="corpus", description="MongoDB collection to search.")
    source: str = Field(default="", description="Source label filter.")
    date_from: str = Field(default="", description="ISO date range start (for by_date).")
    date_to: str = Field(default="", description="ISO date range end (for by_date).")
    document_id: str = Field(default="", description="Document _id for the 'context' operation.")
    context_window: int = Field(default=3, description="Neighbors to fetch for 'context'.", ge=1, le=20)
    limit: int = Field(default=20, description="Max results.", ge=1, le=200)
    score_threshold: float = Field(default=0.3, description="Min similarity score for semantic/hybrid.", ge=0.0, le=1.0)
    qdrant_collection: str = Field(default="", description="Qdrant collection for semantic/hybrid. Uses default if omitted.")


async def run_hud_search(params: HudSearchInput, ctx: Context) -> str:
    conns = get_connections(ctx)
    op = params.operation.strip().lower()
    mongo_coll = conns.mongo_db[params.collection]

    try:
        if op == "keyword":
            if not params.query:
                return err("'query' is required for keyword search")
            filter_doc: dict = {"$text": {"$search": params.query}}
            if params.source:
                filter_doc["_source"] = params.source
            results = list(mongo_coll.find(filter_doc, {"score": {"$meta": "textScore"}}, limit=params.limit).sort([("score", {"$meta": "textScore"})]))
            return ok(results)

        if op == "semantic":
            if not params.query:
                return err("'query' is required for semantic search")
            from fastembed import TextEmbedding
            embedder = TextEmbedding(model_name=conns.embedding_model)
            vector = list(next(embedder.embed([params.query])))
            qcoll = params.qdrant_collection or conns.qdrant_default_collection
            results = await conns.qdrant.search(collection_name=qcoll, query_vector=vector, limit=params.limit, score_threshold=params.score_threshold, with_payload=True)
            return ok([{"id": str(r.id), "score": r.score, "payload": r.payload} for r in results])

        if op == "hybrid":
            if not params.query:
                return err("'query' is required for hybrid search")
            kw_filter: dict = {}
            if params.source:
                kw_filter["_source"] = params.source
            try:
                kw_filter["$text"] = {"$search": params.query}
                kw_results = list(mongo_coll.find(kw_filter, limit=params.limit))
            except Exception:
                kw_results = []
            from fastembed import TextEmbedding
            embedder = TextEmbedding(model_name=conns.embedding_model)
            vector = list(next(embedder.embed([params.query])))
            qcoll = params.qdrant_collection or conns.qdrant_default_collection
            sem_results = await conns.qdrant.search(collection_name=qcoll, query_vector=vector, limit=params.limit, score_threshold=params.score_threshold, with_payload=True)
            return ok({"keyword_results": kw_results, "semantic_results": [{"id": str(r.id), "score": r.score, "payload": r.payload} for r in sem_results]})

        if op == "by_source":
            if not params.source:
                return err("'source' is required for by_source")
            return ok(list(mongo_coll.find({"_source": params.source}, limit=params.limit)))

        if op == "by_date":
            date_filter: dict = {}
            if params.date_from:
                date_filter["$gte"] = params.date_from
            if params.date_to:
                date_filter["$lte"] = params.date_to
            if not date_filter:
                return err("Provide at least one of 'date_from' or 'date_to'")
            return ok(list(mongo_coll.find({"_created_date": date_filter}, limit=params.limit)))

        if op == "context":
            if not params.document_id:
                return err("'document_id' is required for context")
            from bson import ObjectId
            try:
                doc = mongo_coll.find_one({"_id": ObjectId(params.document_id)})
            except Exception:
                doc = mongo_coll.find_one({"_id": params.document_id})
            if not doc:
                return err(f"Document '{params.document_id}' not found")
            source_file = doc.get("_source_file", "")
            if source_file:
                neighbors = list(mongo_coll.find({"_source_file": source_file}, limit=params.context_window * 2 + 1))
                return ok({"target": doc, "neighbors": neighbors})
            return ok({"target": doc, "neighbors": []})

        return err(f"Unknown operation: '{op}'")
    except Exception as e:
        return err(str(e))


# ============================================================================
# hud_extract
# ============================================================================

EXTRACT_OPERATIONS = (
    "from_text       — extract named entities from a provided text string",
    "from_document   — extract entities from a corpus document by ID",
    "from_collection — extract and store entities from an entire collection",
    "get_term        — retrieve a stored entity/term by name",
    "list_terms      — list all stored entities, optionally filtered by type",
    "merge_terms     — merge two entity records (alias deduplication)",
    "delete_term     — delete an entity record",
)


class HudExtractInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    operation: str = Field(..., description="Extract operation. Valid values:\n" + "\n".join(f"  {o}" for o in EXTRACT_OPERATIONS))
    text: str = Field(default="", description="Text to extract entities from (for from_text).")
    document_id: str = Field(default="", description="MongoDB document _id (for from_document).")
    collection: str = Field(default="corpus", description="MongoDB collection to read from.")
    terms_collection: str = Field(default="terms", description="MongoDB collection where extracted terms are stored.")
    term_name: str = Field(default="", description="Entity/term name (for get_term, merge_terms, delete_term).")
    term_type: str = Field(default="", description="Entity type filter: 'person', 'place', 'concept', 'work', etc.")
    merge_into: str = Field(default="", description="Target term name to merge into (for merge_terms).")
    limit: int = Field(default=50, description="Max terms to return for list_terms.", ge=1, le=500)


async def run_hud_extract(params: HudExtractInput, ctx: Context) -> str:
    conns = get_connections(ctx)
    op = params.operation.strip().lower()
    corpus_coll = conns.mongo_db[params.collection]
    terms_coll = conns.mongo_db[params.terms_collection]

    try:
        if op == "from_text":
            if not params.text:
                return err("'text' is required for from_text")
            return ok(_extract_entities_simple(params.text))

        if op == "from_document":
            if not params.document_id:
                return err("'document_id' is required for from_document")
            from bson import ObjectId
            try:
                doc = corpus_coll.find_one({"_id": ObjectId(params.document_id)})
            except Exception:
                doc = corpus_coll.find_one({"_id": params.document_id})
            if not doc:
                return err(f"Document '{params.document_id}' not found")
            entities = _extract_entities_simple(doc.get("content", "") or str(doc))
            stored = 0
            for ent in entities:
                existing = terms_coll.find_one({"name": ent["text"], "type": ent["type"]})
                if not existing:
                    terms_coll.insert_one({"name": ent["text"], "type": ent["type"], "occurrences": [params.document_id]})
                    stored += 1
                else:
                    terms_coll.update_one({"_id": existing["_id"]}, {"$addToSet": {"occurrences": params.document_id}})
            return ok({"entities_found": len(entities), "new_terms_stored": stored, "entities": entities})

        if op == "from_collection":
            docs = list(corpus_coll.find({}, {"content": 1, "_id": 1}, limit=500))
            total_stored = 0
            for doc in docs:
                text = doc.get("content", "")
                if not text:
                    continue
                for ent in _extract_entities_simple(text):
                    doc_id = str(doc["_id"])
                    existing = terms_coll.find_one({"name": ent["text"], "type": ent["type"]})
                    if not existing:
                        terms_coll.insert_one({"name": ent["text"], "type": ent["type"], "occurrences": [doc_id]})
                        total_stored += 1
                    else:
                        terms_coll.update_one({"_id": existing["_id"]}, {"$addToSet": {"occurrences": doc_id}})
            return ok({"docs_processed": len(docs), "new_terms_stored": total_stored})

        if op == "get_term":
            if not params.term_name:
                return err("'term_name' is required for get_term")
            filt: dict = {"name": {"$regex": params.term_name, "$options": "i"}}
            if params.term_type:
                filt["type"] = params.term_type
            return ok(terms_coll.find_one(filt))

        if op == "list_terms":
            filt = {}
            if params.term_type:
                filt["type"] = params.term_type
            return ok(list(terms_coll.find(filt, limit=params.limit).sort("name", 1)))

        if op == "merge_terms":
            if not params.term_name or not params.merge_into:
                return err("'term_name' and 'merge_into' are required for merge_terms")
            source = terms_coll.find_one({"name": params.term_name})
            target = terms_coll.find_one({"name": params.merge_into})
            if not source:
                return err(f"Term '{params.term_name}' not found")
            if not target:
                return err(f"Target term '{params.merge_into}' not found")
            merged = list(set(target.get("occurrences", []) + source.get("occurrences", [])))
            terms_coll.update_one({"_id": target["_id"]}, {"$set": {"occurrences": merged}, "$addToSet": {"aliases": params.term_name}})
            terms_coll.delete_one({"_id": source["_id"]})
            return ok({"merged": params.term_name, "into": params.merge_into, "total_occurrences": len(merged)})

        if op == "delete_term":
            if not params.term_name:
                return err("'term_name' is required for delete_term")
            result = terms_coll.delete_one({"name": params.term_name})
            return ok({"deleted": result.deleted_count, "term": params.term_name})

        return err(f"Unknown operation: '{op}'")
    except Exception as e:
        return err(str(e))


def _extract_entities_simple(text: str) -> list[dict]:
    """Basic capitalized-noun heuristic. Replace with spaCy for production."""
    import re
    words = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', text)
    seen: dict[str, dict] = {}
    for w in words:
        if w not in seen:
            seen[w] = {"text": w, "type": "unknown", "count": 0}
        seen[w]["count"] += 1
    return sorted(seen.values(), key=lambda x: -x["count"])


# ============================================================================
# hud_relate
# ============================================================================

RELATE_OPERATIONS = (
    "create      — create a relationship between two entities in Neo4j",
    "get         — get relationships for a given entity",
    "delete      — delete a specific relationship",
    "find_path   — find the shortest path between two entities",
    "neighborhood — get all nodes within N hops of an entity",
    "pattern     — run a custom graph pattern query",
)


class HudRelateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    operation: str = Field(..., description="Relate operation. Valid values:\n" + "\n".join(f"  {o}" for o in RELATE_OPERATIONS))
    entity_a: str = Field(default="", description="Name or ID of the first/source entity.")
    entity_b: str = Field(default="", description="Name or ID of the second/target entity.")
    entity_type: str = Field(default="Entity", description="Neo4j node label for entity_a/entity_b.")
    relationship_type: str = Field(default="RELATED_TO", description="Neo4j relationship type, e.g. 'MENTIONS', 'APPEARS_IN'.")
    properties: str = Field(default="{}", description="JSON properties to attach to the relationship.")
    direction: str = Field(default="outgoing", description="Relationship direction: 'outgoing', 'incoming', or 'both'.")
    hops: int = Field(default=2, description="Number of hops for neighborhood queries.", ge=1, le=5)
    pattern: str = Field(default="", description="Custom Cypher MATCH pattern for the 'pattern' operation.")
    limit: int = Field(default=50, description="Max results.", ge=1, le=500)


async def run_hud_relate(params: HudRelateInput, ctx: Context) -> str:
    conns = get_connections(ctx)
    op = params.operation.strip().lower()

    try:
        props = json.loads(params.properties or "{}")

        if op == "create":
            if not params.entity_a or not params.entity_b:
                return err("'entity_a' and 'entity_b' are required for create")
            cypher = (f"MERGE (a:{params.entity_type} {{name: $name_a}}) "
                      f"MERGE (b:{params.entity_type} {{name: $name_b}}) "
                      f"MERGE (a)-[r:{params.relationship_type}]->(b) SET r += $props RETURN type(r) as rel_type")
            async with conns.neo4j.session() as session:
                result = await session.run(cypher, name_a=params.entity_a, name_b=params.entity_b, props=props)
                records = [dict(r) async for r in result]
            return ok({"created": True, "relationship": records})

        if op == "get":
            if not params.entity_a:
                return err("'entity_a' is required for get")
            if params.direction == "outgoing":
                match = "MATCH (a {name: $name})-[r]->(b)"
            elif params.direction == "incoming":
                match = "MATCH (a)<-[r]-(b {name: $name})"
            else:
                match = "MATCH (a {name: $name})-[r]-(b)"
            cypher = f"{match} RETURN type(r) as rel, b.name as target, properties(r) as props LIMIT {params.limit}"
            async with conns.neo4j.session() as session:
                result = await session.run(cypher, name=params.entity_a)
                records = [dict(r) async for r in result]
            return ok(records)

        if op == "delete":
            if not params.entity_a or not params.entity_b:
                return err("'entity_a' and 'entity_b' are required for delete")
            cypher = (f"MATCH (a {{name: $name_a}})-[r:{params.relationship_type}]->(b {{name: $name_b}}) "
                      f"DELETE r RETURN count(r) as deleted")
            async with conns.neo4j.session() as session:
                result = await session.run(cypher, name_a=params.entity_a, name_b=params.entity_b)
                records = [dict(r) async for r in result]
            return ok(records)

        if op == "find_path":
            if not params.entity_a or not params.entity_b:
                return err("'entity_a' and 'entity_b' are required for find_path")
            cypher = (f"MATCH path = shortestPath((a {{name: $name_a}})-[*..{params.hops}]-(b {{name: $name_b}})) "
                      f"RETURN [n in nodes(path) | n.name] as path_nodes, length(path) as length")
            async with conns.neo4j.session() as session:
                result = await session.run(cypher, name_a=params.entity_a, name_b=params.entity_b)
                records = [dict(r) async for r in result]
            return ok(records)

        if op == "neighborhood":
            if not params.entity_a:
                return err("'entity_a' is required for neighborhood")
            cypher = (f"MATCH (a {{name: $name}})-[*1..{params.hops}]-(neighbor) "
                      f"RETURN DISTINCT neighbor.name as name, labels(neighbor) as types LIMIT {params.limit}")
            async with conns.neo4j.session() as session:
                result = await session.run(cypher, name=params.entity_a)
                records = [dict(r) async for r in result]
            return ok(records)

        if op == "pattern":
            if not params.pattern:
                return err("'pattern' is required for the pattern operation")
            async with conns.neo4j.session() as session:
                result = await session.run(f"{params.pattern} LIMIT {params.limit}")
                records = [dict(r) async for r in result]
            return ok(records)

        return err(f"Unknown operation: '{op}'")
    except Exception as e:
        return err(str(e))


# ============================================================================
# hud_order
# ============================================================================

ORDER_OPERATIONS = (
    "set_created         — assign a creation/publication date to a document",
    "set_referenced      — assign a referenced historical period to a document",
    "get_timeline        — retrieve documents sorted chronologically",
    "query_by_created    — find documents by their creation date range",
    "query_by_referenced — find documents by the historical period they reference",
    "list_undated        — list documents with no date assigned",
)


class HudOrderInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    operation: str = Field(..., description="Order operation. Valid values:\n" + "\n".join(f"  {o}" for o in ORDER_OPERATIONS))
    document_id: str = Field(default="", description="MongoDB document _id to set dates on.")
    collection: str = Field(default="corpus", description="MongoDB collection to operate on.")
    created_date: str = Field(default="", description="ISO date the document was created/published, e.g. '2023-11-15'.")
    referenced_date_from: str = Field(default="", description="Start of the historical period the document references.")
    referenced_date_to: str = Field(default="", description="End of the historical period the document references.")
    date_from: str = Field(default="", description="Start of date range for query operations.")
    date_to: str = Field(default="", description="End of date range for query operations.")
    limit: int = Field(default=50, description="Max documents to return.", ge=1, le=500)
    source: str = Field(default="", description="Optional source label filter.")


async def run_hud_order(params: HudOrderInput, ctx: Context) -> str:
    conns = get_connections(ctx)
    op = params.operation.strip().lower()
    coll = conns.mongo_db[params.collection]

    try:
        if op == "set_created":
            if not params.document_id or not params.created_date:
                return err("'document_id' and 'created_date' are required")
            from bson import ObjectId
            try:
                filt = {"_id": ObjectId(params.document_id)}
            except Exception:
                filt = {"_id": params.document_id}
            result = coll.update_one(filt, {"$set": {"_created_date": params.created_date}})
            return ok({"matched": result.matched_count, "modified": result.modified_count})

        if op == "set_referenced":
            if not params.document_id:
                return err("'document_id' is required")
            from bson import ObjectId
            try:
                filt = {"_id": ObjectId(params.document_id)}
            except Exception:
                filt = {"_id": params.document_id}
            update: dict = {}
            if params.referenced_date_from:
                update["_referenced_from"] = params.referenced_date_from
            if params.referenced_date_to:
                update["_referenced_to"] = params.referenced_date_to
            if not update:
                return err("Provide at least one of 'referenced_date_from' or 'referenced_date_to'")
            result = coll.update_one(filt, {"$set": update})
            return ok({"matched": result.matched_count, "modified": result.modified_count})

        if op == "get_timeline":
            filt: dict = {"_created_date": {"$exists": True}}
            if params.source:
                filt["_source"] = params.source
            return ok(list(coll.find(filt, limit=params.limit).sort("_created_date", 1)))

        if op == "query_by_created":
            date_filter: dict = {}
            if params.date_from:
                date_filter["$gte"] = params.date_from
            if params.date_to:
                date_filter["$lte"] = params.date_to
            if not date_filter:
                return err("Provide at least one of 'date_from' or 'date_to'")
            filt = {"_created_date": date_filter}
            if params.source:
                filt["_source"] = params.source
            return ok(list(coll.find(filt, limit=params.limit).sort("_created_date", 1)))

        if op == "query_by_referenced":
            filt = {"_referenced_from": {"$exists": True}}
            if params.date_from:
                filt["_referenced_from"] = {"$gte": params.date_from}
            if params.date_to:
                filt["_referenced_to"] = {"$lte": params.date_to}
            if params.source:
                filt["_source"] = params.source
            return ok(list(coll.find(filt, limit=params.limit).sort("_referenced_from", 1)))

        if op == "list_undated":
            filt = {"_created_date": {"$exists": False}, "_referenced_from": {"$exists": False}}
            if params.source:
                filt["_source"] = params.source
            return ok(list(coll.find(filt, limit=params.limit)))

        return err(f"Unknown operation: '{op}'")
    except Exception as e:
        return err(str(e))


# ============================================================================
# hud_annotate
# ============================================================================

ANNOTATE_OPERATIONS = (
    "tag                    — add a tag to a document",
    "untag                  — remove a tag from a document",
    "note                   — add a text note to a document",
    "list_notes             — list all notes on a document",
    "create_collection      — create a named collection of documents",
    "add_to_collection      — add a document to a named collection",
    "remove_from_collection — remove a document from a named collection",
    "list_collections       — list all named collections",
    "get_collection         — get all documents in a named collection",
    "export_collection      — export a named collection to JSON",
)


class HudAnnotateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    operation: str = Field(..., description="Annotate operation. Valid values:\n" + "\n".join(f"  {o}" for o in ANNOTATE_OPERATIONS))
    document_id: str = Field(default="", description="MongoDB document _id to annotate.")
    corpus_collection: str = Field(default="corpus", description="MongoDB collection containing the documents.")
    annotations_collection: str = Field(default="annotations", description="MongoDB collection storing annotations.")
    tag: str = Field(default="", description="Tag string to add or remove.")
    note_text: str = Field(default="", description="Note text to attach to a document.")
    collection_name: str = Field(default="", description="Name of a named document collection.")
    collection_description: str = Field(default="", description="Description for a new named collection.")


async def run_hud_annotate(params: HudAnnotateInput, ctx: Context) -> str:
    conns = get_connections(ctx)
    op = params.operation.strip().lower()
    corpus = conns.mongo_db[params.corpus_collection]
    ann = conns.mongo_db[params.annotations_collection]
    named_colls = conns.mongo_db["named_collections"]

    try:
        if op == "tag":
            if not params.document_id or not params.tag:
                return err("'document_id' and 'tag' are required for tag")
            ann.update_one({"_doc_id": params.document_id}, {"$addToSet": {"tags": params.tag}}, upsert=True)
            return ok({"tagged": params.document_id, "tag": params.tag})

        if op == "untag":
            if not params.document_id or not params.tag:
                return err("'document_id' and 'tag' are required for untag")
            ann.update_one({"_doc_id": params.document_id}, {"$pull": {"tags": params.tag}})
            return ok({"untagged": params.document_id, "tag": params.tag})

        if op == "note":
            if not params.document_id or not params.note_text:
                return err("'document_id' and 'note_text' are required for note")
            import datetime
            ann.update_one({"_doc_id": params.document_id},
                           {"$push": {"notes": {"text": params.note_text, "added": datetime.datetime.utcnow().isoformat()}}},
                           upsert=True)
            return ok({"noted": params.document_id})

        if op == "list_notes":
            if not params.document_id:
                return err("'document_id' is required for list_notes")
            record = ann.find_one({"_doc_id": params.document_id})
            return ok(record.get("notes", []) if record else [])

        if op == "create_collection":
            if not params.collection_name:
                return err("'collection_name' is required for create_collection")
            if named_colls.find_one({"name": params.collection_name}):
                return ok({"exists": True, "name": params.collection_name})
            named_colls.insert_one({"name": params.collection_name, "description": params.collection_description, "document_ids": []})
            return ok({"created": params.collection_name})

        if op == "add_to_collection":
            if not params.collection_name or not params.document_id:
                return err("'collection_name' and 'document_id' are required")
            named_colls.update_one({"name": params.collection_name}, {"$addToSet": {"document_ids": params.document_id}}, upsert=True)
            return ok({"added": params.document_id, "to": params.collection_name})

        if op == "remove_from_collection":
            if not params.collection_name or not params.document_id:
                return err("'collection_name' and 'document_id' are required")
            named_colls.update_one({"name": params.collection_name}, {"$pull": {"document_ids": params.document_id}})
            return ok({"removed": params.document_id, "from": params.collection_name})

        if op == "list_collections":
            results = list(named_colls.find({}, {"name": 1, "description": 1, "document_ids": 1}))
            return ok([{"name": r.get("name"), "description": r.get("description", ""), "count": len(r.get("document_ids", []))} for r in results])

        if op == "get_collection":
            if not params.collection_name:
                return err("'collection_name' is required for get_collection")
            record = named_colls.find_one({"name": params.collection_name})
            if not record:
                return err(f"Collection '{params.collection_name}' not found")
            from bson import ObjectId
            docs = []
            for did in record.get("document_ids", []):
                try:
                    doc = corpus.find_one({"_id": ObjectId(did)})
                except Exception:
                    doc = corpus.find_one({"_id": did})
                if doc:
                    docs.append(doc)
            return ok({"name": params.collection_name, "documents": docs})

        if op == "export_collection":
            if not params.collection_name:
                return err("'collection_name' is required for export_collection")
            record = named_colls.find_one({"name": params.collection_name})
            if not record:
                return err(f"Collection '{params.collection_name}' not found")
            from bson import ObjectId
            docs = []
            for did in record.get("document_ids", []):
                try:
                    doc = corpus.find_one({"_id": ObjectId(did)})
                except Exception:
                    doc = corpus.find_one({"_id": did})
                if doc:
                    docs.append(doc)
            return ok({"name": params.collection_name, "description": record.get("description", ""), "count": len(docs), "documents": docs})

        return err(f"Unknown operation: '{op}'")
    except Exception as e:
        return err(str(e))


# ============================================================================
# hud_report
# ============================================================================

REPORT_OPERATIONS = (
    "statistics — corpus overview: document counts, sources, date coverage",
    "summarize  — summarize a named collection or search result set",
    "export     — export a collection or query result as formatted document",
    "compare    — compare two sources or collections side by side",
    "overview   — full overview of what has been built (corpus + terms + graph)",
)


class HudReportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    operation: str = Field(..., description="Report operation. Valid values:\n" + "\n".join(f"  {o}" for o in REPORT_OPERATIONS))
    collection: str = Field(default="corpus", description="Primary MongoDB collection to report on.")
    collection_a: str = Field(default="", description="First named collection or source for compare.")
    collection_b: str = Field(default="", description="Second named collection or source for compare.")
    export_format: str = Field(default="json", description="Export format: 'json' or 'markdown'.")
    limit: int = Field(default=100, description="Max documents to include in exports/summaries.", ge=1, le=1000)


async def run_hud_report(params: HudReportInput, ctx: Context) -> str:
    conns = get_connections(ctx)
    op = params.operation.strip().lower()
    coll = conns.mongo_db[params.collection]

    try:
        if op == "statistics":
            return ok({
                "corpus_documents": coll.count_documents({}),
                "sources": coll.distinct("_source"),
                "documents_with_created_date": coll.count_documents({"_created_date": {"$exists": True}}),
                "documents_with_referenced_period": coll.count_documents({"_referenced_from": {"$exists": True}}),
                "extracted_terms": conns.mongo_db["terms"].count_documents({}),
                "named_collections": conns.mongo_db["named_collections"].count_documents({}),
                "annotated_documents": conns.mongo_db["annotations"].count_documents({}),
            })

        if op == "compare":
            if not params.collection_a or not params.collection_b:
                return err("'collection_a' and 'collection_b' are required for compare")
            count_a = coll.count_documents({"_source": params.collection_a})
            count_b = coll.count_documents({"_source": params.collection_b})
            terms_a = set(conns.mongo_db["terms"].distinct("name", {"occurrences": {"$elemMatch": {"$regex": params.collection_a}}}))
            terms_b = set(conns.mongo_db["terms"].distinct("name", {"occurrences": {"$elemMatch": {"$regex": params.collection_b}}}))
            shared = terms_a & terms_b
            return ok({
                params.collection_a: {"documents": count_a, "unique_terms": len(terms_a)},
                params.collection_b: {"documents": count_b, "unique_terms": len(terms_b)},
                "shared_terms": list(shared)[:50],
                "shared_term_count": len(shared),
            })

        if op == "overview":
            stats = json.loads(await run_hud_report(HudReportInput(operation="statistics", collection=params.collection), ctx))
            top_terms = list(conns.mongo_db["terms"].find({}, {"name": 1, "type": 1}, sort=[("occurrences", -1)], limit=20))
            named = list(conns.mongo_db["named_collections"].find({}, {"name": 1, "description": 1, "document_ids": 1}))
            return ok({
                "statistics": stats.get("result", {}),
                "top_terms": top_terms,
                "named_collections": [{"name": n.get("name"), "description": n.get("description", ""), "count": len(n.get("document_ids", []))} for n in named],
            })

        if op in ("summarize", "export"):
            docs = list(coll.find({}, limit=params.limit))
            if params.export_format == "markdown":
                lines = [f"# Export: {params.collection}\n", f"**Total documents:** {len(docs)}\n"]
                for doc in docs:
                    content = doc.get("content", "")
                    if content:
                        lines.append(f"\n---\n\n{content[:500]}...")
                return ok({"format": "markdown", "content": "\n".join(lines)})
            return ok({"format": "json", "count": len(docs), "documents": docs})

        return err(f"Unknown operation: '{op}'")
    except Exception as e:
        return err(str(e))