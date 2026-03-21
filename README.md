You wake up somewhere damp. Not wet, precisely — damp. The kind of damp that belongs to old libraries, basement archives, the back rooms of churches where nobody goes anymore. The smell is paper and time and something faintly electrical that you cannot place.

Before you can think too hard about any of this, something small lands on your foot. You look down.

A Hob. Squat, improbable, holding a stack of papers so tall it obscures everything above its waist. It kicks your shoe again — once, twice — and then deposits the whole stack on the floor in front of you with a grunt of effort and what might be professional satisfaction.

From somewhere in the pile it produces a small card and holds it up. Written on it, in very careful letters: "Ἡ γνῶσις οὐχ εὑρίσκεται· κατασκευάζεται."

You do not know Ancient Greek. The Hob seems to find this unsurprising. It flips the card over. The other side says: *Knowledge is not found. It is built.*

The Hob gestures at the papers, at the ceiling, at somewhere beyond the ceiling — at the general concept of *a lot of stuff that needs to make sense* — and then it gestures at you, specifically, with a look of tremendous patience that only a creature who has worked in archives for a very long time can manage.

Then it sits down cross-legged in front of the pile and waits for you to get started.

---

# hob_hud_mcp

A unified MCP server for corpus intelligence — ingesting, indexing, searching, and synthesising large collections of documents across three complementary database layers.

Three databases. Ten tools. One purpose: make sense of vast corpora.

---

## Architecture

Two layers, ten tools total.

**Raw layer** — full access to each database. Use these when the pipeline tools aren't enough.

| Tool | Database | What it gives you |
|------|----------|-------------------|
| `hud_mongo` | MongoDB | Document CRUD, aggregation, text search, schema inference, index management |
| `hud_graph` | Neo4j | Arbitrary Cypher read/write, schema introspection, GDS procedures |
| `hud_vector` | Qdrant | Semantic store/find, collection management, local fastembed embeddings |

**Pipeline layer** — high-level research workflows built on top of the raw layer.

| Tool | Purpose |
|------|---------|
| `hud_ingest` | Load files and directories into the corpus. Auto-detects format (JSON conversation exports, Markdown, JSONL, CSV, plain text). |
| `hud_search` | Retrieve documents by keyword, semantic similarity, or hybrid. Filter by source or date range. |
| `hud_extract` | Extract and catalogue named entities and terms from corpus documents. |
| `hud_relate` | Build and query the knowledge graph — create relationships between entities, find paths, explore neighborhoods. |
| `hud_order` | Assign and query temporal metadata. Maintains two independent date fields: *when a document was written* and *what period it discusses*. |
| `hud_annotate` | Tag documents, add notes, and curate named collections for export. |
| `hud_report` | Statistics, source comparisons, and formatted exports from the corpus. |

---

## Why two date fields?

`hud_order` maintains a `created_date` (when the document was produced) and a `referenced_period` (the historical era the document discusses). These are independent. A 2019 paper about events in 450 BCE needs both.

---

## Tool Reference

### `hud_mongo`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `find`, `find_one`, `insert`, `update`, `delete`, `aggregate`, `count`, `text_search`, `explain`, `export`, `schema`, `stats`, `indexes`, `create_collection`, `drop_collection`, `list_collections`, `list_databases`, `use_database` |
| `database` | `string` | *(configured default)* | Target database name |
| `collection` | `string` | `""` | Target collection |
| `filter` | `string` | `"{}"` | JSON filter document |
| `document` | `string` | `""` | JSON document(s) for insert/update |
| `pipeline` | `string` | `"[]"` | JSON aggregation pipeline |
| `projection` | `string` | `"{}"` | JSON projection |
| `sort` | `string` | `"{}"` | JSON sort spec |
| `limit` | `integer` | `20` | Max documents to return |
| `skip` | `integer` | `0` | Documents to skip (pagination) |
| `query_text` | `string` | `""` | Text for `text_search` |
| `export_format` | `string` | `"json"` | `json` or `csv` |
| `upsert` | `boolean` | `false` | Insert if no match on update |
| `multi` | `boolean` | `true` | Update/delete all matches |

---

### `hud_graph`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `read_cypher`, `write_cypher`, `get_schema`, `list_gds` |
| `cypher` | `string` | `""` | Cypher query string |
| `params` | `string` | `"{}"` | JSON Cypher parameters |
| `limit` | `integer` | `100` | Max rows for read queries |

---

### `hud_vector`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `store`, `find`, `delete`, `list_collections`, `create_collection`, `delete_collection`, `collection_info` |
| `collection` | `string` | *(configured default)* | Qdrant collection name |
| `text` | `string` | `""` | Text to embed and store, or query text |
| `metadata` | `string` | `"{}"` | JSON metadata for stored entries |
| `entry_id` | `string` | *(auto-generated)* | Unique ID for stored entry |
| `limit` | `integer` | `10` | Max results for `find` |
| `score_threshold` | `float` | `0.0` | Min similarity score |
| `vector_size` | `integer` | `384` | Vector dimensions for `create_collection` |

---

### `hud_ingest`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `load_file`, `load_directory`, `preview`, `status`, `list_sources`, `remove_source` |
| `path` | `string` | `""` | Absolute path to file or directory |
| `source_label` | `string` | *(from filename)* | Label for this source, e.g. `claude`, `chatgpt` |
| `collection` | `string` | `"corpus"` | MongoDB collection to store into |
| `format_hint` | `string` | `""` | Optional: `conversation`, `academic`, `notes`, `raw` |
| `recursive` | `boolean` | `true` | Recurse into subdirectories |
| `overwrite` | `boolean` | `false` | Re-ingest already-present files |

---

### `hud_search`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `keyword`, `semantic`, `hybrid`, `by_source`, `by_date`, `context` |
| `query` | `string` | `""` | Search query |
| `collection` | `string` | `"corpus"` | MongoDB collection |
| `source` | `string` | `""` | Source label filter |
| `date_from` | `string` | `""` | ISO date range start |
| `date_to` | `string` | `""` | ISO date range end |
| `document_id` | `string` | `""` | Document `_id` for `context` |
| `context_window` | `integer` | `3` | Neighbors to fetch for `context` |
| `limit` | `integer` | `20` | Max results |
| `score_threshold` | `float` | `0.3` | Min score for semantic/hybrid |

---

### `hud_extract`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `from_text`, `from_document`, `from_collection`, `get_term`, `list_terms`, `merge_terms`, `delete_term` |
| `text` | `string` | `""` | Text to extract from |
| `document_id` | `string` | `""` | MongoDB document `_id` |
| `collection` | `string` | `"corpus"` | Source corpus collection |
| `terms_collection` | `string` | `"terms"` | Where extracted terms are stored |
| `term_name` | `string` | `""` | Term name to look up or merge |
| `term_type` | `string` | `""` | Filter by type: `person`, `place`, `concept`, `work` |
| `merge_into` | `string` | `""` | Target term for merge |
| `limit` | `integer` | `50` | Max terms for `list_terms` |

---

### `hud_relate`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `create`, `get`, `delete`, `find_path`, `neighborhood`, `pattern` |
| `entity_a` | `string` | `""` | Source entity name |
| `entity_b` | `string` | `""` | Target entity name |
| `entity_type` | `string` | `"Entity"` | Neo4j node label |
| `relationship_type` | `string` | `"RELATED_TO"` | Neo4j relationship type |
| `properties` | `string` | `"{}"` | JSON relationship properties |
| `direction` | `string` | `"outgoing"` | `outgoing`, `incoming`, or `both` |
| `hops` | `integer` | `2` | Depth for `neighborhood` and `find_path` |
| `pattern` | `string` | `""` | Custom Cypher pattern for `pattern` |
| `limit` | `integer` | `50` | Max results |

---

### `hud_order`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `set_created`, `set_referenced`, `get_timeline`, `query_by_created`, `query_by_referenced`, `list_undated` |
| `document_id` | `string` | `""` | MongoDB document `_id` |
| `collection` | `string` | `"corpus"` | Target collection |
| `created_date` | `string` | `""` | ISO date the document was written |
| `referenced_date_from` | `string` | `""` | Start of referenced historical period |
| `referenced_date_to` | `string` | `""` | End of referenced historical period |
| `date_from` | `string` | `""` | Query range start |
| `date_to` | `string` | `""` | Query range end |
| `source` | `string` | `""` | Optional source filter |
| `limit` | `integer` | `50` | Max results |

---

### `hud_annotate`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `tag`, `untag`, `note`, `list_notes`, `create_collection`, `add_to_collection`, `remove_from_collection`, `list_collections`, `get_collection`, `export_collection` |
| `document_id` | `string` | `""` | Target document `_id` |
| `tag` | `string` | `""` | Tag to add or remove |
| `note_text` | `string` | `""` | Note text to attach |
| `collection_name` | `string` | `""` | Named collection |
| `collection_description` | `string` | `""` | Description for new collection |

---

### `hud_report`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `operation` | `string` | *(required)* | `statistics`, `summarize`, `export`, `compare`, `overview` |
| `collection` | `string` | `"corpus"` | Primary collection |
| `collection_a` | `string` | `""` | First source for `compare` |
| `collection_b` | `string` | `""` | Second source for `compare` |
| `export_format` | `string` | `"json"` | `json` or `markdown` |
| `limit` | `integer` | `100` | Max documents in exports |

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/Corykidios/hob_hud_mcp
cd hob_hud_mcp
pip install -e .
```

### 2. Configure

```bash
copy .env.example .env
# edit .env with your values
```

### 3. Start your databases

MongoDB and Neo4j need to be running. Qdrant can run as a server or in local file mode (set `QDRANT_LOCAL_PATH` in `.env` to skip the server entirely).

### 4. Configure in Letta or Claude Desktop

```json
{
  "mcpServers": {
    "hob_hud": {
      "command": "python",
      "args": ["-m", "hob_hud_mcp.server"],
      "cwd": "C:/c/apps/servers/hob_hud_mcp"
    }
  }
}
```

---

## Requirements

- Python 3.11+
- MongoDB (running locally or remote)
- Neo4j with APOC plugin
- Qdrant (server or local path mode)

---

## With Many Thanks

This server stands on the shoulders of three excellent open-source projects:

**[furey/mongodb-lens](https://github.com/furey/mongodb-lens)** by James Furey — a full-featured MongoDB MCP server with natural language access, schema inference, aggregation pipelines, and more. The breadth of what mongodb-lens covers in a single file is genuinely impressive, and `hud_mongo` would not have its depth without it as a reference.

**[neo4j/mcp](https://github.com/neo4j/mcp)** — the official Neo4j MCP server, built in Go, clean and fast. Four tools that give you everything: arbitrary Cypher, schema introspection, GDS. The design philosophy of trusting the user with raw query access rather than wrapping it in fragile abstractions is exactly right.

**[qdrant/mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant)** — the official Qdrant server. Python, FastMCP, local fastembed embeddings that cost nothing to run. The decision to ship with a local embedding model by default rather than requiring an external API key is a small design choice that makes a real difference for people trying to build without a budget.

All three are actively maintained, well-documented, and worth starring in their own right. If `hob_hud_mcp` is useful to you, please consider giving them the credit they're owed. As for me, I have only a very partial understanding of what I have assembled here, and I am grateful every day that these people wrote things I could learn from.