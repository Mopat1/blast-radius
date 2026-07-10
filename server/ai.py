"""AI impact explanations using Google Gemini."""

from __future__ import annotations

import os
from google import genai

MODEL = os.environ.get("BLASTRADIUS_AI_MODEL", "gemini-2.5-flash")


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _summarize(report: dict) -> str:
    def head(xs, n=12):
        xs = xs or []
        return ", ".join(xs[:n]) + (" …" if len(xs) > n else "")

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
        f"Hidden dependencies ({len(report.get('coupled_files', []))}): "
        f"{head(report.get('coupled_files', []))}"
    )


def explain_impact(report: dict) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "AI explanations are not configured (set GEMINI_API_KEY)."
        )

    client = genai.Client(api_key=api_key)

    prompt = (
        "You are a senior software engineer reviewing a pull request.\n\n"
        "Using the blast radius report below, explain:\n"
        "1. What is likely to break.\n"
        "2. Why the risk score is reasonable.\n"
        "3. Which tests should be executed first.\n"
        "4. Hidden dependencies to review.\n\n"
        + _summarize(report)
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    return response.text.strip()
