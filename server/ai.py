"""AI impact explanations.

Follows the BlastRadius AI-layer principle: the model never sees raw
code — it receives structured context from the engine (impact report,
coupling, metadata) and writes a reviewer-style note.

Requires ANTHROPIC_API_KEY in the environment; endpoints return 503
when unset so the feature degrades gracefully.
"""

from __future__ import annotations

import os

import httpx

MODEL = os.environ.get("BLASTRADIUS_AI_MODEL", "claude-sonnet-4-6")
API_URL = "https://api.anthropic.com/v1/messages"


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _summarize(report: dict) -> str:
    head = lambda xs, n=12: ", ".join(xs[:n]) + (" …" if len(xs) > n else "")
    return (
        f"Target: {report['target']}\n"
        f"Risk score: {report['risk_score']} ({report['risk_level']}), "
        f"call depth {report['call_depth']}\n"
        f"Affected functions ({len(report['affected_functions'])}): "
        f"{head(report['affected_functions'])}\n"
        f"Affected API endpoints ({len(report['affected_endpoints'])}): "
        f"{head(report['affected_endpoints'])}\n"
        f"Tests covering the change ({len(report['affected_tests'])}): "
        f"{head(report['affected_tests'])}\n"
        f"Hidden dependencies from git co-change history "
        f"({len(report.get('coupled_files', []))}): "
        f"{head(report.get('coupled_files', []))}"
    )


def explain_impact(report: dict) -> str:
    prompt = (
        "You are a senior engineer writing a short code-review note.\n"
        "Below is the computed blast radius of changing one function in a "
        "codebase, produced by static call-graph analysis plus git history "
        "mining. Write a plain-text note (no markdown, 120-180 words, 2-3 "
        "short paragraphs) covering: what this change realistically touches, "
        "why the risk score is at this level, and what a reviewer should "
        "focus on — including which tests to prioritize and any hidden "
        "co-change dependencies to double-check.\n\n" + _summarize(report)
    )
    resp = httpx.post(
        API_URL,
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": MODEL, "max_tokens": 500,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text").strip()
