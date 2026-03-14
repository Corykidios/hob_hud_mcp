# Hob HUD — MCP Server

> *A heads-up display for AI database access.*

**10 tools. Two databases. One server.**

Hob HUD gives any MCP-compatible AI agent direct, structured access to a local Neo4j graph database and Qdrant vector store — plus a high-level GraphRAG pipeline layered on top of both.

Built as part of the Penedi memory infrastructure: a personal knowledge graph for navigating 32,000+ AI conversations, recovering lost personas, and tracing the shape of a life through language.

---

## Tools

### GraphRAG Pipeline (3 tools)
| Tool | Description |
|------|-------------|
| `ask_graph_rag` | Query the knowledge graph with natural language |
| `ingest_to_graph` | Extract entities + relationships from text and store permanently |
| `clear_graph` | Wipe the GraphRAG store (destructive — ask first) |

### Neo4j — Direct Cypher Access (3 tools)
| Tool | Description |
|------|-------------|
| `neo4j_schema` | Inspect labels, relationship types, properties, indexes, constraints |
| `neo4j_read` | Execute any read-only Cypher query |
| `neo4j_write` | Execute any write Cypher query (CREATE, MERGE, SET, DELETE) |

### Qdrant — Direct Vector Store Access (4 tools)
| Tool | Description |
|------|-------------|
| `qdrant_collections` | List, create, inspect, or delete collections |
| `qdrant_store` | Embed text and store it with metadata |
| `qdrant_search` | Semantic search with optional metadata filters |
| `qdrant_points` | Count, retrieve, scroll, or delete raw points |

---

## Requirements

- Python 3.10+
- Running Neo4j instance (default: `bolt://localhost:7687`)
- Running Qdrant instance (default: `localhost:6333`)
- An OpenAI-compatible embedding endpoint (tested with NVIDIA NIM)

```
pip install mcp fastmcp neo4j qdrant-client openai python-dotenv
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

QDRANT_HOST=localhost
QDRANT_PORT=6333

OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
OPENAI_API_KEY=your_nim_key
OPENAI_EMBEDDING_MODEL=nvidia/nv-embedqa-e5-v5
OPENAI_VECTOR_DIMENSION=1024
OPENAI_INFERENCE_MODEL=meta/llama-3.3-70b-instruct

# Path to graph_rag project (needed for GraphRAG pipeline tools)
HOB_HUD_GRAPH_RAG_DIR=C:\path\to\Qdrant-Neo4j-Ollama-Graph-Rag
HOB_HUD_ENV=C:\path\to\Qdrant-Neo4j-Ollama-Graph-Rag\.env
```

---

## Claude Desktop

```json
"hob_hud": {
  "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
  "args": ["C:\\c\\apps\\hob_hud_mcp\\server.py"]
}
```

## Letta

Register as a stdio MCP server pointing to `server.py` using the same venv Python.

---

## Architecture

```
hob_hud_mcp/
├── server.py        ← single-file MCP server (all 10 tools)
├── .env.example
└── README.md
```

The GraphRAG tools depend on the `Qdrant-Neo4j-Ollama-Graph-Rag` project being cloned and configured separately. The Neo4j and Qdrant tools are fully standalone.

---

## Name

*Hob* — a crafting surface, the flat top of a hearth. A place where things are made.  
*HUD* — heads-up display. What you see when you need to act without looking away.

Part of the **Penedi** project.
