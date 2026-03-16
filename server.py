"""
hob_hud_mcp — Cori's MCP server. Mercury/Air/Hill.
GraphRAG hybrid retrieval: Neo4j + Qdrant + Mistral embeddings.
10 tools. 51 operations.
"""

import sys
import os
import json
import logging
import hashlib
from typing import Optional

sys.path.insert(0, r'C:/c/apps/servers/graphrag-hybrid/src')

from dotenv import load_dotenv
load_dotenv(r'C:/c/apps/servers/hob_hud_mcp/.env')

from fastmcp import FastMCP
from mistral_embedder import MistralEmbedder
from database.neo4j_manager import Neo4jManager
from database.qdrant_manager import QdrantManager
from query_engine import QueryEngine
from qdrant_client.http import models as qmodels

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


class Cfg:
    def __init__(self):
        self._d = {
            "neo4j": {
                "uri":      os.environ.get("NEO4J_URI",      "bolt://localhost:7687"),
                "http_uri": os.environ.get("NEO4J_HTTP_URI", "http://localhost:7474"),
                "username": os.environ.get("NEO4J_USERNAME", "neo4j"),
                "password": os.environ.get("NEO4J_PASSWORD", "password"),
                "database": os.environ.get("NEO4J_DATABASE", "neo4j"),
            },
            "qdrant": {
                "host":        os.environ.get("QDRANT_HOST",        "localhost"),
                "port":        int(os.environ.get("QDRANT_PORT",        6333)),
                "grpc_port":   int(os.environ.get("QDRANT_GRPC_PORT",   6334)),
                "prefer_grpc": os.environ.get("QDRANT_PREFER_GRPC", "true").lower() == "true",
                "collection":  os.environ.get("QDRANT_COLLECTION",  "document_chunks"),
            },
            "embedding": {
                "model_name":  os.environ.get("EMBEDDING_MODEL_NAME",  "mistral-embed"),
                "vector_size": int(os.environ.get("EMBEDDING_VECTOR_SIZE", 1024)),
                "device":      "api",
                "max_length":  int(os.environ.get("EMBEDDING_MAX_LENGTH", 512)),
            },
        }

    def get(self, key: str, default=None):
        parts = key.split(".")
        val = self._d
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return default
            if val is None:
                return default
        return val


NOTES_COLLECTION = "hud_notes"
VECTOR_SIZE      = int(os.environ.get("EMBEDDING_VECTOR_SIZE", 1024))

config   = Cfg()
embedder = MistralEmbedder()
neo4j    = Neo4jManager(config)
neo4j.connect()
qdrant   = QdrantManager(config, embedding_model=embedder)
qdrant.connect()
engine   = QueryEngine(neo4j, qdrant, embedding_processor=embedder)

try:
    cols = [c.name for c in qdrant.client.get_collections().collections]
    if NOTES_COLLECTION not in cols:
        qdrant.client.create_collection(
            collection_name=NOTES_COLLECTION,
            vectors_config=qmodels.VectorParams(size=VECTOR_SIZE, distance=qmodels.Distance.COSINE)
        )
except Exception as e:
    logger.warning(f"Could not ensure notes collection: {e}")

mcp = FastMCP("hob_hud")


@mcp.tool()
def hud_search(
    operation: str,
    query:        Optional[str] = None,
    limit:        int           = 5,
    category:     Optional[str] = None,
    doc_id:       Optional[str] = None,
    chunk_id:     Optional[str] = None,
    context_size: int           = 2,
) -> str:
    """
    Search and retrieval. operation: hybrid | semantic | category | related | expand_context
    hybrid(query,limit,category) semantic(query,limit,category) category(category,limit)
    related(doc_id,limit) expand_context(chunk_id,context_size)
    """
    op = operation.lower()
    if op == "hybrid":
        return json.dumps(engine.hybrid_search(query, limit=limit, category=category), indent=2, default=str)
    elif op == "semantic":
        return json.dumps(engine.semantic_search(query, limit=limit, category=category), indent=2, default=str)
    elif op == "category":
        return json.dumps(engine.category_search(category, limit=limit), indent=2, default=str)
    elif op == "related":
        return json.dumps(engine.suggest_related(doc_id, limit=limit), indent=2, default=str)
    elif op == "expand_context":
        return json.dumps(engine.expand_context(chunk_id, context_size=context_size), indent=2, default=str)
    return json.dumps({"error": f"Unknown: {op}", "valid": ["hybrid","semantic","category","related","expand_context"]})


@mcp.tool()
def hud_graph(
    operation: str,
    query:  Optional[str] = None,
    params: Optional[str] = None,
) -> str:
    """
    Neo4j operations. operation: read | write | schema | stats | categories | clear
    read(query,params) write(query,params) schema() stats() categories() clear()
    """
    op = operation.lower()
    p  = json.loads(params) if params else {}
    if op == "read":
        with neo4j.driver.session() as s:
            records = [dict(r) for r in s.run(query, p)]
        return json.dumps(records, indent=2, default=str)
    elif op == "write":
        with neo4j.driver.session() as s:
            summary = s.run(query, p).consume()
        return json.dumps({"counters": dict(summary.counters)}, indent=2, default=str)
    elif op == "schema":
        with neo4j.driver.session() as s:
            labels    = s.run("CALL db.labels()").data()
            rel_types = s.run("CALL db.relationshipTypes()").data()
        return json.dumps({"labels": labels, "relationship_types": rel_types}, indent=2, default=str)
    elif op == "stats":
        return json.dumps(neo4j.get_statistics(), indent=2, default=str)
    elif op == "categories":
        return json.dumps(engine.get_all_categories(), indent=2, default=str)
    elif op == "clear":
        neo4j.clear_database()
        return json.dumps({"ok": True, "message": "Neo4j cleared."})
    return json.dumps({"error": f"Unknown: {op}", "valid": ["read","write","schema","stats","categories","clear"]})


@mcp.tool()
def hud_vector(
    operation:       str,
    information:     Optional[str] = None,
    query:           Optional[str] = None,
    collection_name: Optional[str] = None,
    metadata:        Optional[str] = None,
    limit:           int           = 5,
    filter_json:     Optional[str] = None,
    vector_size:     int           = 1024,
) -> str:
    """
    Qdrant operations. operation: store | find | scroll | list | info | create | delete
    store(information,collection_name,metadata) find(query,collection_name,limit)
    scroll(collection_name,limit,filter_json) list() info(collection_name)
    create(collection_name,vector_size) delete(collection_name)
    """
    op   = operation.lower()
    coll = collection_name or os.environ.get("QDRANT_COLLECTION", "document_chunks")
    if op == "store":
        meta   = json.loads(metadata) if metadata else {}
        vector = embedder.get_embedding(information)
        int_id = int(hashlib.md5(information[:64].encode()).hexdigest()[:8], 16)
        qdrant.client.upsert(
            collection_name=coll,
            points=[qmodels.PointStruct(id=int_id, vector=vector, payload={"text": information, **meta})]
        )
        return json.dumps({"ok": True, "id": int_id, "collection": coll})
    elif op == "find":
        vector  = embedder.get_embedding(query)
        results = qdrant.client.search(collection_name=coll, query_vector=vector, limit=limit)
        return json.dumps([{"score": r.score, "text": r.payload.get("text",""), "payload": r.payload} for r in results], indent=2, default=str)
    elif op == "scroll":
        filt = None
        if filter_json:
            raw        = json.loads(filter_json)
            conditions = [qmodels.FieldCondition(key=k, match=qmodels.MatchValue(value=v)) for k, v in raw.items()]
            filt       = qmodels.Filter(must=conditions)
        points, _ = qdrant.client.scroll(collection_name=coll, scroll_filter=filt, limit=limit, with_vectors=False)
        return json.dumps([{"id": p.id, "payload": p.payload} for p in points], indent=2, default=str)
    elif op == "list":
        return json.dumps([c.name for c in qdrant.client.get_collections().collections], indent=2)
    elif op == "info":
        return json.dumps(str(qdrant.client.get_collection(coll)), indent=2)
    elif op == "create":
        qdrant.client.create_collection(collection_name=coll, vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE))
        return json.dumps({"ok": True, "created": coll})
    elif op == "delete":
        qdrant.client.delete_collection(coll)
        return json.dumps({"ok": True, "deleted": coll})
    return json.dumps({"error": f"Unknown: {op}", "valid": ["store","find","scroll","list","info","create","delete"]})


@mcp.tool()
def hud_doc(
    operation: str,
    doc_id:    Optional[str] = None,
    category:  Optional[str] = None,
    limit:     int           = 10,
) -> str:
    """
    Document operations. operation: get | list | chunks | related | delete
    get(doc_id) list(category,limit) chunks(doc_id) related(doc_id,limit) delete(doc_id)
    """
    op = operation.lower()
    if op == "get":
        return json.dumps(engine.get_document_with_chunks(doc_id), indent=2, default=str)
    elif op == "list":
        if category:
            return json.dumps(engine.category_search(category, limit=limit), indent=2, default=str)
        with neo4j.driver.session() as s:
            records = [dict(r) for r in s.run("MATCH (d:Document) RETURN d LIMIT $limit", {"limit": limit})]
        return json.dumps(records, indent=2, default=str)
    elif op == "chunks":
        return json.dumps(neo4j.get_document_chunks(doc_id), indent=2, default=str)
    elif op == "related":
        return json.dumps(neo4j.get_related_documents(doc_id, limit=limit), indent=2, default=str)
    elif op == "delete":
        with neo4j.driver.session() as s:
            summary = s.run("MATCH (d:Document {id: $id}) DETACH DELETE d", {"id": doc_id}).consume()
        return json.dumps({"ok": True, "counters": dict(summary.counters)}, indent=2, default=str)
    return json.dumps({"error": f"Unknown: {op}", "valid": ["get","list","chunks","related","delete"]})


@mcp.tool()
def hud_chunk(
    operation:    str,
    chunk_id:     Optional[str] = None,
    doc_id:       Optional[str] = None,
    context_size: int           = 1,
    limit:        int           = 10,
    filter_json:  Optional[str] = None,
) -> str:
    """
    Chunk operations. operation: get | context | by_doc | count
    get(chunk_id) context(chunk_id,context_size) by_doc(doc_id,limit) count(filter_json)
    """
    op = operation.lower()
    if op == "get":
        return json.dumps(qdrant.get_by_id(chunk_id), indent=2, default=str)
    elif op == "context":
        return json.dumps(neo4j.get_chunk_context(chunk_id, context_size=context_size), indent=2, default=str)
    elif op == "by_doc":
        return json.dumps(neo4j.get_document_chunks(doc_id)[:limit], indent=2, default=str)
    elif op == "count":
        filt = json.loads(filter_json) if filter_json else None
        return json.dumps({"count": qdrant.get_count(filt)}, indent=2, default=str)
    return json.dumps({"error": f"Unknown: {op}", "valid": ["get","context","by_doc","count"]})


@mcp.tool()
def hud_ingest(
    operation:       str,
    path:            Optional[str] = None,
    collection_name: Optional[str] = None,
) -> str:
    """
    Ingestion pipeline. operation: status | check | import_file | import_dir
    status() check() import_file(path) import_dir(path)
    """
    op = operation.lower()
    if op == "status":
        log_path = r"C:/c/apps/servers/graphrag-hybrid/import_docs.log"
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return json.dumps({"last_lines": lines[-20:]}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
    elif op == "check":
        result = {}
        try:
            neo4j.driver.verify_connectivity()
            result["neo4j"] = "ok"
        except Exception as e:
            result["neo4j"] = str(e)
        try:
            qdrant.client.get_collections()
            result["qdrant"] = "ok"
        except Exception as e:
            result["qdrant"] = str(e)
        return json.dumps(result, indent=2)
    elif op in ("import_file", "import_dir"):
        import subprocess
        python = r"C:/c/apps/servers/graphrag-hybrid/venv/Scripts/python.exe"
        script = r"C:/c/apps/servers/graphrag-hybrid/scripts/import_docs.py"
        target = path if op == "import_dir" else str(os.path.dirname(path))
        proc   = subprocess.Popen([python, script, "--docs-dir", target, "--recursive"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return json.dumps({"ok": True, "pid": proc.pid, "message": f"Ingestion started PID {proc.pid}."})
    return json.dumps({"error": f"Unknown: {op}", "valid": ["status","check","import_file","import_dir"]})


@mcp.tool()
def hud_note(
    operation: str,
    text:      Optional[str] = None,
    query:     Optional[str] = None,
    note_id:   Optional[int] = None,
    tags:      Optional[str] = None,
    limit:     int           = 10,
) -> str:
    """
    AI scratchpad in Qdrant 'hud_notes'. operation: store | find | list | delete | clear
    store(text,tags) find(query,limit) list(limit) delete(note_id) clear()
    Any AI can store observations, connections, working hypotheses here.
    """
    op = operation.lower()
    if op == "store":
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        vector   = embedder.get_embedding(text)
        int_id   = int(hashlib.md5(text[:64].encode()).hexdigest()[:8], 16)
        qdrant.client.upsert(
            collection_name=NOTES_COLLECTION,
            points=[qmodels.PointStruct(id=int_id, vector=vector, payload={"text": text, "tags": tag_list})]
        )
        return json.dumps({"ok": True, "id": int_id})
    elif op == "find":
        vector  = embedder.get_embedding(query)
        results = qdrant.client.search(collection_name=NOTES_COLLECTION, query_vector=vector, limit=limit)
        return json.dumps([{"score": r.score, "id": r.id, "text": r.payload.get("text",""), "tags": r.payload.get("tags",[])} for r in results], indent=2, default=str)
    elif op == "list":
        points, _ = qdrant.client.scroll(collection_name=NOTES_COLLECTION, limit=limit, with_vectors=False)
        return json.dumps([{"id": p.id, "text": p.payload.get("text",""), "tags": p.payload.get("tags",[])} for p in points], indent=2, default=str)
    elif op == "delete":
        qdrant.client.delete(collection_name=NOTES_COLLECTION, points_selector=qmodels.PointIdsList(points=[note_id]))
        return json.dumps({"ok": True, "deleted": note_id})
    elif op == "clear":
        qdrant.client.delete_collection(NOTES_COLLECTION)
        qdrant.client.create_collection(collection_name=NOTES_COLLECTION, vectors_config=qmodels.VectorParams(size=VECTOR_SIZE, distance=qmodels.Distance.COSINE))
        return json.dumps({"ok": True, "message": "Notes cleared."})
    return json.dumps({"error": f"Unknown: {op}", "valid": ["store","find","list","delete","clear"]})


@mcp.tool()
def hud_relate(
    operation:  str,
    doc_id:     Optional[str] = None,
    target_id:  Optional[str] = None,
    rel_type:   Optional[str] = None,
    depth:      int           = 2,
    limit:      int           = 10,
) -> str:
    """
    Graph relationship ops. operation: add | remove | traverse | neighbors | path
    add(doc_id,target_id,rel_type) remove(doc_id,target_id,rel_type)
    traverse(doc_id,depth,limit) neighbors(doc_id,limit) path(doc_id,target_id)
    """
    op = operation.lower()
    rt = rel_type or "RELATED_TO"
    if op == "add":
        with neo4j.driver.session() as s:
            s.run(f"MATCH (a:Document {{id:$a}}),(b:Document {{id:$b}}) MERGE (a)-[:{rt}]->(b)", {"a": doc_id, "b": target_id})
        return json.dumps({"ok": True, "rel": rt, "from": doc_id, "to": target_id})
    elif op == "remove":
        with neo4j.driver.session() as s:
            s.run(f"MATCH (a:Document {{id:$a}})-[r:{rt}]->(b:Document {{id:$b}}) DELETE r", {"a": doc_id, "b": target_id})
        return json.dumps({"ok": True, "removed": rt})
    elif op == "traverse":
        with neo4j.driver.session() as s:
            records = [dict(r) for r in s.run(
                f"MATCH (a:Document {{id:$id}})-[*1..{depth}]-(b:Document) RETURN DISTINCT b LIMIT $limit",
                {"id": doc_id, "limit": limit}
            )]
        return json.dumps(records, indent=2, default=str)
    elif op == "neighbors":
        return json.dumps(neo4j.get_related_documents(doc_id, limit=limit), indent=2, default=str)
    elif op == "path":
        with neo4j.driver.session() as s:
            records = [dict(r) for r in s.run(
                "MATCH p=shortestPath((a:Document {id:$a})-[*]-(b:Document {id:$b})) RETURN p",
                {"a": doc_id, "b": target_id}
            )]
        return json.dumps(records, indent=2, default=str)
    return json.dumps({"error": f"Unknown: {op}", "valid": ["add","remove","traverse","neighbors","path"]})


@mcp.tool()
def hud_filter(
    operation:  str,
    subject:    Optional[str] = None,
    provider:   Optional[str] = None,
    date_from:  Optional[str] = None,
    date_to:    Optional[str] = None,
    concept:    Optional[str] = None,
    query:      Optional[str] = None,
    limit:      int           = 10,
) -> str:
    """
    Compound filtered queries over your archive structure.
    operation: by_subject | by_provider | by_date | by_concept | by_category
    by_subject(subject,limit) by_provider(provider,limit) by_date(date_from,date_to,limit)
    by_concept(concept,query,limit) by_category(provider,subject,query,limit)
    """
    op = operation.lower()
    if op == "by_subject":
        with neo4j.driver.session() as s:
            records = [dict(r) for r in s.run(
                "MATCH (d:Document) WHERE d.category CONTAINS $subject RETURN d LIMIT $limit",
                {"subject": subject, "limit": limit}
            )]
        return json.dumps(records, indent=2, default=str)
    elif op == "by_provider":
        with neo4j.driver.session() as s:
            records = [dict(r) for r in s.run(
                "MATCH (d:Document) WHERE d.category STARTS WITH $provider RETURN d LIMIT $limit",
                {"provider": provider, "limit": limit}
            )]
        return json.dumps(records, indent=2, default=str)
    elif op == "by_date":
        cypher = "MATCH (d:Document) WHERE 1=1"
        params: dict = {"limit": limit}
        if date_from:
            cypher += " AND d.updated >= $from"
            params["from"] = date_from
        if date_to:
            cypher += " AND d.updated <= $to"
            params["to"] = date_to
        cypher += " RETURN d LIMIT $limit"
        with neo4j.driver.session() as s:
            records = [dict(r) for r in s.run(cypher, params)]
        return json.dumps(records, indent=2, default=str)
    elif op == "by_concept":
        with neo4j.driver.session() as s:
            records = [dict(r) for r in s.run(
                "MATCH (d:Document)-[:HAS_CONCEPT]->(c:Concept {name:$concept}) RETURN d LIMIT $limit",
                {"concept": concept, "limit": limit}
            )]
        if query and records:
            sem = engine.semantic_search(query, limit=limit)
            return json.dumps({"graph_results": records, "semantic_rerank": sem}, indent=2, default=str)
        return json.dumps(records, indent=2, default=str)
    elif op == "by_category":
        category = "/".join(filter(None, [provider, subject]))
        sem = engine.semantic_search(query or "", limit=limit, category=category or None)
        return json.dumps(sem, indent=2, default=str)
    return json.dumps({"error": f"Unknown: {op}", "valid": ["by_subject","by_provider","by_date","by_concept","by_category"]})


@mcp.tool()
def hud_health(operation: str) -> str:
    """
    System diagnostics. operation: stats | ping | schema_summary | collection_summary | full_report
    stats() ping() schema_summary() collection_summary() full_report()
    """
    op = operation.lower()
    if op == "stats":
        return json.dumps(engine.get_statistics(), indent=2, default=str)
    elif op == "ping":
        result = {}
        try:
            neo4j.driver.verify_connectivity()
            result["neo4j"] = "ok"
        except Exception as e:
            result["neo4j"] = str(e)
        try:
            qdrant.client.get_collections()
            result["qdrant"] = "ok"
        except Exception as e:
            result["qdrant"] = str(e)
        return json.dumps(result, indent=2)
    elif op == "schema_summary":
        with neo4j.driver.session() as s:
            labels    = s.run("CALL db.labels()").data()
            rel_types = s.run("CALL db.relationshipTypes()").data()
            constrs   = s.run("SHOW CONSTRAINTS").data()
        return json.dumps({"labels": labels, "relationship_types": rel_types, "constraints": constrs}, indent=2, default=str)
    elif op == "collection_summary":
        cols     = qdrant.client.get_collections().collections
        summary  = []
        for c in cols:
            try:
                info = qdrant.client.get_collection(c.name)
                summary.append({"name": c.name, "vectors": info.vectors_count})
            except Exception:
                summary.append({"name": c.name, "vectors": "unknown"})
        return json.dumps(summary, indent=2, default=str)
    elif op == "full_report":
        report = {}
        report["stats"]       = engine.get_statistics()
        report["ping"]        = json.loads(hud_health("ping"))
        report["collections"] = json.loads(hud_health("collection_summary"))
        with neo4j.driver.session() as s:
            report["labels"]    = s.run("CALL db.labels()").data()
            report["rel_types"] = s.run("CALL db.relationshipTypes()").data()
        return json.dumps(report, indent=2, default=str)
    return json.dumps({"error": f"Unknown: {op}", "valid": ["stats","ping","schema_summary","collection_summary","full_report"]})


if __name__ == "__main__":
    mcp.run()