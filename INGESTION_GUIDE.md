# Neo4j + Qdrant Ingestion — Care & Recovery Guide
*For Cory or any AI helping Cory*

## What's Running

A two-phase ingestion of 28,407 conversations (19,682,945 chunks) into a
hybrid GraphRAG database. Started 2026-03-16 around 02:00.

| Database | Container | Port | Purpose |
|----------|-----------|------|---------|
| Neo4j | graphrag_neo4j | 7687 (bolt), 7474 (http) | Graph structure, relationships |
| Qdrant | graphrag_qdrant | 6333 (http), 6334 (grpc) | Vector embeddings |

Source docs: `D:/graphrag_gang/docs/`  
Log file: `C:/c/apps/servers/graphrag-hybrid/import_docs.log`  
Embedder: Mistral API (`mistral-embed`), 1 RPS free tier

---

## The Two Phases

**Phase 1 — Neo4j** (fast, no API calls)  
All 28,407 documents and their chunks written to Neo4j as nodes and
relationships. Pure database writes. This phase is silent in the log.

**Phase 2 — Qdrant** (slow, Mistral API calls)  
Each chunk gets embedded via Mistral at ~1 request per second and stored
in Qdrant. This is the long phase — days of continuous running.

---

## How To Check Progress

```powershell
# See last log entries
powershell -Command "Get-Content C:\c\apps\servers\graphrag-hybrid\import_docs.log -Tail 10"

# Confirm process is alive
powershell -Command "Get-Process python | Select-Object Id, CPU, WorkingSet"

# Check Docker containers are up
docker ps
```

If the log shows "Uploading batch" or "Processed X chunks" — Phase 2 is
running. If it's silent and a python process has high CPU — Phase 1 is
running.

---

## How To Pause Safely

Go to the terminal running `import_docs.py` and press **Ctrl+C**.

That's it. Both databases keep whatever was written. Nothing is corrupted.

---

## How To Resume

**If interrupted during Phase 1 (Neo4j):**  
Re-run with `--clear` flag to wipe and restart cleanly. Neo4j's batch
import doesn't have a checkpoint system.

```
cd C:\c\apps\servers\graphrag-hybrid
venv\Scripts\activate
python scripts/import_docs.py --docs-dir D:/graphrag_gang/docs --recursive --clear
```

**If interrupted during Phase 2 (Qdrant):**  
Neo4j is already complete. Only Qdrant needs to be redone. For now,
re-run the full import — a resume-from-checkpoint script hasn't been
built yet. Add `--clear` only if you want to wipe Neo4j too.

---

## If Docker Containers Stop

```powershell
cd C:\c\apps\servers\graphrag-hybrid
docker-compose up -d
```

Verify both are running:
```powershell
docker ps
```
You should see `graphrag_neo4j` and `graphrag_qdrant` both `Up`.

---

## Do Not

- Do not delete the `D:/graphrag_gang/` folder
- Do not run `docker-compose down -v` — the `-v` flag wipes the volumes
- Do not run `import_docs.py` with `--clear` unless you intend a full restart
- Do not kill the Docker containers while ingestion is writing

---

## After It Finishes

Run `get_statistics` from hob_hud_mcp to confirm counts, then
`get_neo4j_schema` to see what the graph looks like. The MCP server
at `C:/c/apps/servers/hob_hud_mcp/` is already live and waiting.

*Written 2026-03-16 — the grand ingestion, hour ten.*