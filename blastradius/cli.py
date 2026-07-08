"""BlastRadius CLI.

    blastradius analyze <repo>                       # parse repo, summarize graph
    blastradius impact  <repo> --target <function>   # blast radius of one function
    blastradius graph   <repo> -o graph.json         # export IR/graph as JSON
"""

from __future__ import annotations

import json
import sys

import click

from .parser.python_parser import PythonParser
from .engine import build_graph, BlastEngine
from .ir import NodeKind

BLAST = click.style("●", fg="red")
SAFE = click.style("●", fg="blue")


def _build(repo: str):
    doc = PythonParser(repo).parse()
    return doc, build_graph(doc)


@click.group()
@click.version_option("0.2.0", prog_name="blastradius")
def main():
    """Know what breaks before you merge."""


@main.command()
@click.argument("repo", type=click.Path(exists=True, file_okay=False))
def analyze(repo):
    """Parse REPO and print a summary of the dependency graph."""
    doc, g = _build(repo)
    kinds = {}
    for n in doc.nodes:
        kinds[n.kind.value] = kinds.get(n.kind.value, 0) + 1

    click.secho("\nBlastRadius — repository analysis", bold=True)
    click.echo(f"root: {doc.root}\n")
    for kind in ("module", "class", "function", "method", "test", "api_endpoint"):
        if kind in kinds:
            click.echo(f"  {kinds[kind]:>4}  {kind}")
    click.echo(f"\n  {g.number_of_edges():>4}  edges (CALLS / IMPORTS / CONTAINS / EXPOSES / TESTS / INHERITS)")

    # top 5 most-depended-on functions
    engine = BlastEngine(g)
    scored = []
    for n, data in g.nodes(data=True):
        if data.get("kind") in ("function", "method"):
            r = engine.blast_radius(n)
            scored.append((r.risk_score, n, r))
    scored.sort(reverse=True)
    if scored:
        click.secho("\nhighest blast radius:", bold=True)
        for risk, name, r in scored[:5]:
            color = "red" if r.risk_level == "HIGH" else "yellow" if r.risk_level == "MEDIUM" else "green"
            click.echo(f"  {click.style(f'{risk:>5.2f}', fg=color)}  {name}  "
                       f"({len(r.affected_functions)} callers, {len(r.affected_endpoints)} endpoints)")
    click.echo()


@main.command()
@click.argument("repo", type=click.Path(exists=True, file_okay=False))
@click.option("--target", "-t", required=True, help="Function name (short or fully qualified).")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def impact(repo, target, as_json):
    """Compute the blast radius of TARGET inside REPO."""
    _, g = _build(repo)
    engine = BlastEngine(g)

    matches = engine.find(target)
    if not matches:
        click.secho(f"error: no node matching {target!r}", fg="red", err=True)
        sys.exit(1)
    if len(matches) > 1 and target not in matches:
        click.secho(f"ambiguous target {target!r}; candidates:", fg="yellow", err=True)
        for m in matches[:10]:
            click.echo(f"  {m}", err=True)
        sys.exit(1)

    report = engine.blast_radius(matches[0])

    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}[report.risk_level]
    click.secho(f"\n{BLAST} blast radius: {report.target}", bold=True)
    click.echo(f"  risk: {click.style(f'{report.risk_score} ({report.risk_level})', fg=color, bold=True)}"
               f"   call depth: {report.call_depth}\n")

    _section("affected functions", report.affected_functions)
    _section("affected files", report.affected_files)
    _section("affected endpoints", report.affected_endpoints)
    _section("tests to run", report.affected_tests)
    click.echo()


def _section(title, items):
    click.secho(f"  {title} ({len(items)})", bold=True)
    for item in items or ["—"]:
        click.echo(f"    {item}")
    click.echo()


@main.command("diff")
@click.argument("repo", type=click.Path(exists=True, file_okay=False))
@click.option("--base", default="HEAD", show_default=True,
              help="Git ref to diff against (e.g. origin/main).")
@click.option("--head", default=None,
              help="Git ref for the new side. Omit to use the working tree.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON.")
@click.option("--github", "as_github", is_flag=True,
              help="Markdown formatted as a GitHub PR comment.")
def diff_cmd(repo, base, head, as_json, as_github):
    """Blast radius of everything that changed between two git refs."""
    from .diff import diff_impact, to_markdown
    try:
        d = diff_impact(repo, base=base, head=head)
    except Exception as exc:
        click.secho(f"error: {exc}", fg="red", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(d.to_dict(), indent=2))
        return
    if as_github:
        click.echo(to_markdown(d))
        return

    if not d.changed_functions:
        click.echo(f"No Python function changes between {d.base} and {d.head}.")
        return
    c = d.combined
    color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}[c.risk_level]
    click.secho(f"\n{BLAST} diff impact: {d.base} -> {d.head}", bold=True)
    click.echo(f"  combined risk: {click.style(f'{c.risk_score} ({c.risk_level})', fg=color, bold=True)}"
               f"   call depth: {c.call_depth}\n")
    click.secho(f"  changed functions ({len(d.changed_functions)})", bold=True)
    for fid, r in sorted(d.reports.items(), key=lambda kv: -kv[1].risk_score):
        rc = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}[r.risk_level]
        click.echo(f"    {click.style(f'{r.risk_score:>6.1f}', fg=rc)}  {fid}")
    click.echo()
    _section("affected endpoints", c.affected_endpoints)
    _section("tests to run", c.affected_tests)
    if d.unmapped_files:
        _section("changed outside functions (not analyzed)", d.unmapped_files)
    click.echo()


@main.command()
@click.argument("repo", type=click.Path(exists=True, file_okay=False))
@click.option("--output", "-o", default="blastradius-graph.json", show_default=True)
def graph(repo, output):
    """Export the full IR graph of REPO as JSON."""
    doc, _ = _build(repo)
    with open(output, "w", encoding="utf-8") as f:
        f.write(doc.to_json())
    click.echo(f"wrote {len(doc.nodes)} nodes / {len(doc.edges)} edges -> {output}")


if __name__ == "__main__":
    main()
