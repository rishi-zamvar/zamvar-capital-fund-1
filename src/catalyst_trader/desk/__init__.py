"""The analyst desk (Workflow 1a): a plain-async Python orchestrator over the
Claude Agent SDK. Analysts fan out, bull/bear debate in real context isolation,
a moderator emits a binary verdict, a verifier enforces source-quote-or-drop.

Every role call routes through the ONE seam in `desk.runtime.run_structured`, the
single monkeypatch point that keeps the whole suite offline. The orchestrator
entry (`run_desk`) lives in `desk/orchestrator.py` (Plan 07), not here.
"""

MAX_ROUNDS = 2  # TradingAgents max_debate_rounds; cost-bound, small book
