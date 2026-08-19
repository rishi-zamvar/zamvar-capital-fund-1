# Slice 0 — Live-LLM smoke test RESULT (2026-08-19)

**Verdict: PASS. The desk's live LLM runtime is validated. The single load-bearing unknown is retired.**

Runtime decision (CEO): Max subscription, agents run inside Claude Code, NO API key.

## Stage 1 — structured output + auth
- `run_structured(prompt, schema, model="sonnet")` ran a REAL call with `ANTHROPIC_API_KEY` UNSET → the Claude Agent SDK `query()` inherited the Max auth of the Claude Code environment.
- Returned validated `json_schema` structured output (sum=42), latency **~9.8s**.
- **Confirms:** the desk runs against a real model with no API key, under Max/inside-CC, exactly as designed (`.env` comment was right).

## Stage 2 — in-process quant MCP tool-calling
- Built `build_quant_server(:memory: conn)`, forced a `mcp__quant__rnpv` call (allowed_tools=["mcp__quant__rnpv"]).
- Model returned `rnpv_value=268.8939992451061` — **matches the deterministic `quant.rnpv` to full float precision** → the model genuinely invoked the in-process tool (can't fake that precision), latency **~11.4s**.
- **Confirms:** the analysts' cite-or-drop foundation works live — the model calls the in-process quant/KB tools and receives the real deterministic values; the mocks in the test suite match live behavior.

## Cost / latency
- ~10-11s per sonnet call. A catalyst = ~30-40 calls (4 analysts + debate rounds + moderator + builder + 3 risk views + synthesis + memo/premortem/pm + 8 DD dims + up to 3 MD rounds), several on opus (slower). With the desk's `asyncio.gather` fan-out, wall-clock is minutes/catalyst, not the sum. **$0 marginal cost on Max** (within subscription limits) when run inside Claude Code.

## Consequences for the milestone
- The runtime assumption underpinning the ENTIRE agentic desk is validated — proceed to wire.
- No API-key management needed; the weekly run is launched inside a Claude Code session (not pure headless cron) — acceptable per the CEO runtime decision.
- Smoke scripts (`slice0_smoke.py`, `slice0_smoke_tools.py`) are manual/live artifacts — NOT added to the offline test suite (they make real LLM calls). Kept as reproducible evidence.

## Next (Phase 7.8)
Followup 1 (hedge-profile backfill) + Followup 2 (portfolio-builder into weekly assembly), then Slice 1 (one catalyst → live dossier) + Slice 2 (attach the orphaned DD + MD loop).
