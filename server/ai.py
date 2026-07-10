"""AI impact explanations using Google Gemini."""

from __future__ import annotations

import os

from google import genai

MODEL = os.environ.get("BLASTRADIUS_AI_MODEL", "gemini-2.5-flash")
API_KEY = os.environ.get("GEMINI_API_KEY")

_client = genai.Client(api_key=API_KEY) if API_KEY else None


def is_configured() -> bool:
    return _client is not None


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
    if not is_configured():
        raise RuntimeError(
            "AI explanations are not configured (set GEMINI_API_KEY)."
        )

    prompt = (
        "You are a senior software engineer reviewing a code change.\n"
        "Using the blast-radius report below, write a reviewer note of at "
        "most 170 words.\n\n"
        "Respond in EXACTLY this plain-text template. Do not use markdown, "
        "asterisks, hashes, or backticks anywhere:\n\n"
        "SUMMARY: <2-3 sentences: what this change realistically touches>\n"
        "RISK: <1-2 sentences: why the score is at this level>\n"
        "TESTS FIRST:\n"
        "- <highest-priority test> (up to 5 bullets)\n"
        "WATCH OUT:\n"
        "- <hidden dependencies or risky interactions> (up to 4 bullets; "
        "write '- none' if nothing stands out)\n\n"
        + _summarize(report)
    )

    try:
        response = _client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )

        text = getattr(response, "text", None)

        if not text:
            raise RuntimeError("Gemini returned an empty response.")

        return text.strip()

    except Exception as e:
        raise RuntimeError(f"Gemini request failed: {e}") from e