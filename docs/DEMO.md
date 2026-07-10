# The 90-second demo script

Use this order when showing BlastRadius to anyone (recruiter, professor,
interviewer). Every step sets up the next.

**0:00 — The pitch (one sentence).**
"BlastRadius tells you what a code change will break — before you merge it."

**0:10 — Sign in with the demo button.** No signup friction; the account
is preloaded with a real codebase (pallets/click: 1,312 symbols, 5,124
dependency edges, parsed in under a second).

**0:20 — The graph.** Packages collapsed, hover any node: its
neighborhood lights up with labels. "This is the entire codebase as a
dependency graph — calls, tests, API endpoints, inheritance."

**0:35 — Detonate a hotspot.** Open the repo overview, click the top
hotspot (e.g. `strip_ansi`, risk ~209). The blast ripples orange:
"Changing this one function affects 389 others, and these are the exact
tests you'd need to run."

**0:50 — The call chain.** Click any affected function in the panel:
the exact path lights up in yellow. "And here's *why* it's affected —
this precise chain of calls."

**1:00 — Hidden dependencies.** Point at the co-change section: "These
files have no static link to this code, but git history shows they
change together — a dependency no static analyzer can see."

**1:10 — AI review note.** Click ✨ explain: a structured reviewer note
appears (summary, risk, tests first, watch out).

**1:20 — The receipts.** "Resolution accuracy is benchmarked: precision
1.00, recall 0.86, F1 0.92 — the suite runs in CI on every push. And on
GitHub, every pull request gets this analysis as an automatic comment."

**1:30 — Close.** Share the deep link in your address bar: it reopens
exactly this blast radius.
