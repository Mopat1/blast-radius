# Application kit — resume bullets & SOP material

All numbers below are real and reproducible from this repository.

## Resume bullets (pick 2–3)

- Built **BlastRadius**, an open-source code-change impact analysis
  platform (Python AST parser → language-agnostic IR → dependency graph
  → risk-scored blast radius), deployed as a full-stack SaaS (FastAPI,
  PostgreSQL, Cytoscape.js) with JWT auth and background analysis.
- Benchmarked call-graph resolution against a hand-annotated ground-truth
  suite: **precision 1.00, recall 0.86, F1 0.92**; the evaluation runs in
  CI and surfaced a real parser defect during development.
- Fused static analysis with **git history mining (temporal coupling)**
  to flag hidden dependencies invisible to static analyzers, feeding a
  weighted risk model; shipped diff-aware analysis that posts impact
  reports on GitHub pull requests automatically.
- Scaled interactive graph visualization to 1,300+ node repositories
  (package aggregation, fcose layouts, hover-spotlight labels) and added
  AI-generated review notes from structured graph context.

## SOP paragraph (adapt voice as needed)

To understand how research ideas survive contact with real software, I
built BlastRadius, an impact-analysis platform that answers "what breaks
if I change this function?" I designed a two-pass AST parser emitting a
language-agnostic intermediate representation, a graph engine computing
risk-scored blast radii, and — after noticing static analysis misses
dependencies that only history reveals — a temporal-coupling miner that
fuses git co-change data into the risk model. I treated it as a measured
system rather than a demo: a ground-truth benchmark suite (precision
1.00, recall 0.86, F1 0.92) runs in CI, and building it exposed and fixed
a real resolver defect. The project is deployed as a working SaaS and
comments impact reports on pull requests automatically. It taught me the
discipline I want to bring to graduate research: quantify claims, design
for the failure cases, and ship.

## Screenshot checklist for the README

1. Self-analysis: BlastRadius's own repo with a blast radius detonated.
2. Click hotspot detonation (`strip_ansi`) with the impact panel.
3. The AI review-note modal.
4. A PR comment posted by the GitHub Action.
5. The `blastradius eval` terminal table.
