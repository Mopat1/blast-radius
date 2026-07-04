# BlastRadius

**Know what breaks before you merge.**

BlastRadius builds a dependency graph of your codebase and computes the *blast radius* of a code change — affected functions, files, API endpoints, tests to run, and a risk score — before CI fails and before production notices.

```
Repository → Parser → IR → Graph Builder → Graph → Blast Engine → CLI / JSON
```

## Install

```bash
pip install -e .
```

## Usage

```bash
# summarize a repo's dependency graph + top blast radii
blastradius analyze path/to/repo

# blast radius of one function (short or qualified name)
blastradius impact path/to/repo --target calc_tax
blastradius impact path/to/repo --target app.tax.calc_tax --json

# export the full graph as JSON (for dashboards / Neo4j import / AI context)
blastradius graph path/to/repo -o graph.json
```

Example output:

```
● blast radius: app.tax.calc_tax
  risk: 3.0 (HIGH)   call depth: 3

  affected functions (5)   → cart_total, charge, checkout, ...
  affected endpoints (1)   → POST /checkout
  tests to run (2)         → test_charge, test_tax
```

## How it works

1. **Parser** — walks the repo with Python's `ast`, two passes:
   declarations first (modules, classes, functions, endpoints via
   `@app.get/post/route` decorators, tests via naming), then call-site
   resolution (import table → same module → `self.` → unique global name).
2. **IR** — a language-agnostic intermediate representation
   (`IRDocument` of nodes + typed edges). Any future parser
   (JS/TS/Java/Go) emits the same format.
3. **Graph builder** — IR → NetworkX `MultiDiGraph` with typed edges:
   `CALLS`, `IMPORTS`, `CONTAINS`, `INHERITS`, `EXPOSES`, `TESTS`.
4. **Blast engine** — reverse BFS over `CALLS` edges (who transitively
   depends on the changed node), then collects `EXPOSES` endpoints and
   `TESTS` coverage over the affected set.

## Risk score

```
risk = 0.4·callers + 0.3·endpoints + 0.2·tests + 0.1·call_depth
```

`< 1.5` LOW · `1.5–3.0` MEDIUM · `≥ 3.0` HIGH

## Library usage

```python
from blastradius import PythonParser, build_graph, BlastEngine

doc = PythonParser("path/to/repo").parse()
engine = BlastEngine(build_graph(doc))
report = engine.blast_radius("app.tax.calc_tax")
print(report.risk_score, report.affected_endpoints)
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

- [x] Milestone 1 — open-source engine (parser, IR, graph, blast algorithm, CLI, JSON export)
- [x] Milestone 2 — Cloud MVP (JWT auth, repo management, background analysis, dashboard with interactive graph, search, impact API)
- [ ] Milestone 3 — GitHub App, VS Code extension, AI assistant


## BlastRadius Cloud (Milestone 2)

A FastAPI backend + single-page dashboard on top of the engine.

```bash
pip install -e ".[server,dev]"
uvicorn server.main:app --reload
```

Open **http://localhost:8000** — create an account, add a repository
(git URL or local path), and it's analyzed in the background. Click any
node in the graph to detonate its blast radius; the impact panel shows
risk score, affected functions, endpoints, and tests.

Interactive API docs at **http://localhost:8000/docs**.

### API

| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | JWT auth |
| GET/POST/DELETE | `/repos` | repository management |
| POST | `/repos/{id}/analyze` | re-run background analysis |
| GET | `/repos/{id}/graph` | full IR graph as JSON |
| GET | `/repos/{id}/impact?target=fn` | blast radius report |
| GET | `/repos/{id}/search?q=` | node search |

### MVP infrastructure choices (and swap points)

| MVP | Production swap |
|---|---|
| SQLite | PostgreSQL (change `BLASTRADIUS_DB`) |
| FastAPI BackgroundTasks | Celery + Redis (same job function) |
| Graph JSON in SQL | Neo4j |
| Canvas force layout | React Flow / Next.js dashboard |
