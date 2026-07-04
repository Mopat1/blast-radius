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
- [ ] Milestone 2 — Cloud MVP (auth, repos, dashboard, graph visualization)
- [ ] Milestone 3 — GitHub App, VS Code extension, AI assistant
