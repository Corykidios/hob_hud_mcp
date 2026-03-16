# hob_hud_mcp

Cori's MCP server. Mercury / Air / Hill.

Hybrid GraphRAG retrieval over Neo4j + Qdrant with Mistral embeddings. Part of the Echoing Orpheus Studios infrastructure — one of the ten Hob servers, blending three source repositories into a single coherent tool surface.

## Sources

- [rileylemm/graphrag-hybrid](https://github.com/rileylemm/graphrag-hybrid) — core Neo4j+Qdrant database layer
- [swapnilk2/neo4j_mcp](https://github.com/swapnilk2/neo4j_mcp) — Neo4j direct access patterns
- [qdrant/mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant) — Qdrant collection management patterns

## Prerequisites

- Python 3.9+
- Docker (Neo4j + Qdrant via graphrag-hybrid's docker-compose)
- [graphrag-hybrid](https://github.com/rileylemm/graphrag-hybrid) cloned to `C:/c/apps/servers/graphrag-hybrid`
- Mistral API key (free tier)

## Setup

```bash
git clone https://github.com/Corykidios/hob_hud_mcp
cd hob_hud_mcp
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env with your values
python server.py
```

## Tools (10)

| Tool | Description |
|------|-------------|
| `hybrid_search` | Semantic + graph expansion. Best for exploratory retrieval. |
| `semantic_search` | Pure vector similarity against Qdrant. |
| `suggest_related` | Graph traversal from a doc ID. |
| `get_categories` | All categories in the Neo4j graph. |
| `get_statistics` | Full system health: node counts, vector counts. |
| `read_neo4j_cypher` | Run any read Cypher query. |
| `write_neo4j_cypher` | Run any write Cypher query. |
| `get_neo4j_schema` | Labels, relationship types, constraints. |
| `qdrant_list_collections` | All Qdrant collections. |
| `qdrant_collection_info` | Info on a specific collection. |

## Claude Desktop Config

```json
"hob_hud_mcp": {
  "command": "C:\\c\\apps\\servers\\hob_hud_mcp\\venv\\Scripts\\python.exe",
  "args": ["C:\\c\\apps\\servers\\hob_hud_mcp\\server.py"]
}
```