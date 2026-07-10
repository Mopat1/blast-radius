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


## Diff-aware analysis (Milestone 4)

Don't tell BlastRadius what changed — let git do it:

```bash
blastradius diff .                                  # your uncommitted changes vs HEAD
blastradius diff . --base origin/main --head HEAD   # a PR branch vs its target
blastradius diff . --github                         # Markdown PR comment
blastradius diff . --json                           # machine-readable
```

It parses the git diff, maps changed line ranges onto function spans,
and unions the blast radii of every changed function into one combined
risk report.

### PR comments on every pull request

Copy `examples/github-action/blastradius.yml` into `.github/workflows/`
of any Python repo. Every PR gets an auto-updating comment with the
combined risk score, per-function breakdown, exposed endpoints, and the
exact tests to run.

## Measured accuracy (Milestone 6)

Call resolution is evaluated against a curated benchmark suite
(`benchmarks/`, PyCG-style): 12 categories from trivial to known-hard,
each with hand-annotated ground-truth edges. Run it yourself:

```bash
blastradius eval benchmarks
```

| Case | P | R | F1 | Notes |
|---|---|---|---|---|
| ambiguous_name | 1.00 | 1.00 | 1.00 | Imported name resolves; ambiguous x.work() must NOT guess (precision). |
| decorator | 1.00 | 1.00 | 1.00 | Calls to decorated functions still resolve by name. |
| direct_call | 1.00 | 1.00 | 1.00 | Baseline: direct call within one module. |
| dynamic_getattr | 1.00 | 0.00 | 0.00 | getattr(obj, name)() is string-based dispatch: expected recall miss. |
| higher_order | 1.00 | 0.50 | 0.67 | fn() through a parameter is dynamic dispatch: expected recall miss. |
| import_alias | 1.00 | 1.00 | 1.00 | Aliased module and aliased symbol imports. |
| import_from | 1.00 | 1.00 | 1.00 | from X import y resolution via import table. |
| import_module | 1.00 | 1.00 | 1.00 | import X; X.fn() attribute-chain resolution. |
| inheritance_call | 1.00 | 1.00 | 1.00 | self.x() falling back to the (unique) inherited method. |
| method_unique | 1.00 | 1.00 | 1.00 | obj.method() resolved because the method name is globally unique. |
| nested_function | 1.00 | 1.00 | 1.00 | Call to a function defined in the enclosing scope. |
| self_method | 1.00 | 1.00 | 1.00 | self.x() resolved within the same class. |
| **overall (micro)** | **1.00** | **0.86** | **0.92** | 12 TP · 0 FP · 2 FN |


**Precision is 1.0 by design** — the resolver never guesses: ambiguous
names produce no edge. The only recall misses are genuinely dynamic
dispatch (`getattr(obj, name)()` and calls through function-valued
parameters), which no purely static analyzer resolves. The suite runs in
CI on every push, and building it immediately caught a real parser bug
(nested function definitions were not being registered).

## AI review notes (Milestone 6, powered by Gemini)

With `GEMINI_API_KEY` set on the server, every impact report gets an
**✨ explain** button: the impact data (never your raw code) is sent to
Gemini, which writes a reviewer-style note — what realistically breaks,
why the risk is at this level, which tests and hidden dependencies to
check. Without the key the feature degrades gracefully (503).

The note opens in a focused modal with structured sections (summary,
risk, tests first, watch out), a copy button, and Esc to dismiss.

**Shareable deep links:** every detonation updates the URL
(`#r=<repo>&t=<target>`) — share it and the recipient lands on the same
blast radius. **📄 report** downloads any impact report as Markdown.
**Sample repository:** set `BLASTRADIUS_SAMPLE_REPO` (e.g. to this
repo's git URL) and every new account starts with an analyzed example.

Saved layouts now also sync to your account (server-side), with
localStorage as offline fallback.

## Temporal coupling — hidden dependencies (Milestone 5)

Static call graphs can't see every dependency: a config module and the
code that reads it, a serializer and its schema, duplicated logic kept in
sync by hand. Git history can.

```bash
blastradius coupling .                      # top co-changing file pairs
blastradius impact . -t calc_tax --coupling # blast radius + hidden deps
blastradius diff . --coupling --github      # PR comment with a warning section
```

Files that co-change with the target (strength = together / min(changes),
window = last 300 commits, noise-filtered) but sit **outside** the static
blast radius are flagged as hidden dependencies — each adds 0.15 to risk:

```
risk = 0.4*callers + 0.3*endpoints + 0.2*tests + 0.1*depth + 0.15*hidden_deps
```

BlastRadius Cloud computes coupling during analysis (clones now keep 300
commits of history) and shows hidden dependencies in the impact panel.

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
