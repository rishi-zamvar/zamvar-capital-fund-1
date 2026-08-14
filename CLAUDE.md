<!-- GSD:project-start source:PROJECT.md -->
## Project

**Zamvar Capital — Fund 1**

An event-driven trading system for a curated universe of ~20 life-science / biotech stocks. 1–2 days before a major catalyst (FDA PDUFA date, clinical-trial readout, conference presentation, earnings), a layered multi-agent research desk (running as Claude Code subagents) analyzes the firm, the drug, and likelihood indicators, debates bull vs. bear, and produces a recommended one-week portfolio: long/long pairs (a target long hedged by a correlated peer long) sized toward a ~1%/week return. Approved candidates pass through a second, independent due-diligence agent framework before going live. An iOS dashboard surfaces curated KPIs and lets the user review the diligence dossier and approve/reject trades, talking directly to the running Claude Code instances. The system learns continuously via a graph knowledge base of scenario playbooks and outcomes.

**Core Value:** Given an imminent biotech catalyst, produce a data-backed, portfolio-aware, hedged one-week trade recommendation the user can trust enough to approve — and get measurably better at it every week.

### Constraints

- **Execution broker**: Robinhood MCP — assumed equities buy/sell + read only (no options/shorting confirmed yet; research to verify the real tool surface). Long/long pairs work within this.
- **Tech stack**: Claude Code subagents for the agent desk; graph KB leaning embedded (Kùzu) over a Neo4j server unless research says otherwise; iOS = SwiftUI over a Tailscale bridge to the Claude Code host.
- **Return target**: ~1% per week, one-week holds — the objective the strategy and sizing optimize toward.
- **Human gate**: no live trade without explicit user approval; DD pipeline is a hard prerequisite to going live.
- **Paper-first**: 1 month simulated before any real capital.
- **Domain risk**: money-touching + biotech binary events — full rigor (research + plan-check + verifier) is on.
- **Simplicity + readability**: production-ready, but the simplest codebase that works — the user must be able to read and understand it end-to-end. Efficient, minimal dependencies, boring over clever. This never comes at the cost of insight quality: simplify the code, not the analysis.
- **Test coverage**: every new module ships with a full test suite (TDD — tests before logic), exhaustive edge cases, especially on money-critical deterministic tools. No new code without tests.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## The headline decision (Execution)
| Path | Verdict | Why |
|------|---------|-----|
| **Robinhood official Agentic Trading MCP** | ✅ **USE for live execution** | ToS-sanctioned, segregated agent account (agent only touches funds you deposit), per-trade push notifications, disconnect-anytime, equities-only beta = exactly this project's scope. Connect via one MCP URL. |
| `robin_stocks` / `pyrh` / community "Robinhood MCP" wrappers | ❌ **DO NOT USE for execution** | Unofficial, hits private endpoints, explicit "could be withdrawn at any time," no order-confirmation guardrails, account-ban risk. Unacceptable on real money. |
## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Robinhood Agentic Trading MCP** (official) | Beta (live 2026-05-27) | Live equities buy/sell + read portfolio/quotes | Only ToS-safe execution path. Tools observed: `place_equity_order`, `get_portfolio`, `get_equity_quotes`, watchlists, scans, single-leg option orders. Segregated account = money-safety. [Robinhood newsroom](https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/) · [agentic-trading](https://robinhood.com/us/en/agentic-trading/) · **HIGH** |
| **Claude Agent SDK (Python)** | latest (`pip install claude-agent-sdk`, Python 3.10+) | Orchestration runtime for the analyst desk (headless/scheduled) | Native MCP integration, subagents, JSON-Schema structured outputs (`outputFormat` → `structured_output`). Runs programmatically on a schedule (catalyst T-2 trigger) — you can't depend on a human sitting in an interactive session. [SDK guide](https://inference.net/content/claude-agent-sdk-production-guide/) · **HIGH** (feature set) / **LOW** (exact version) |
| **ClinicalTrials.gov API v2** | v2.0 (REST/JSON, OpenAPI 3.0) | Trial registry, primary-completion dates, endpoints, phase, sponsor | Free, no auth, authoritative source of trial-readout timing. Base `https://clinicaltrials.gov/api/v2`. [NLM bulletin](https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html) · **HIGH** |
| **Financial Modeling Prep (FMP) API** | `stable` API, Starter/Premium tier | Quotes, financial statements, cash-flow (→ runway), float/shares outstanding | Best single source for fundamentals + statements + float in one API with clear paid licensing. Free tier = 250 req/day (too small for production). [FMP docs](https://site.financialmodelingprep.com/developer/docs) · **MEDIUM-HIGH** |
| **SQLite + `sqlite-vec`** | SQLite 3.4x + `sqlite-vec` (see verify) | Knowledge base: scenario playbooks, outcomes, provenance/citations, **analog similarity search** | The "analog querying" requirement is vector-similarity, not deep multi-hop traversal. sqlite-vec gives analog search (17ms/k=20 on 1M vecs, M1) + relational provenance in one zero-ops embedded file. See "KB decision" below. [sqlite-vec](https://github.com/asg017/sqlite-vec) · **MEDIUM** |
| **SwiftUI + Swift Charts** | iOS 17+ target | iOS dashboard UI + KPI charts | Apple first-party, no third-party charting dependency. Matches the user's ZeeChat precedent. **HIGH** (official Apple framework) |
| **FastAPI + SSE shim** | FastAPI latest | Transport: iOS ⇄ Claude Code host over Tailscale | Directly reuses the user's proven ZeeChat pattern (HTTP + Server-Sent-Events over Tailscale). Don't reinvent. **HIGH** (user's own established pattern) |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **TauricResearch/TradingAgents** | v0.2.0 (Feb 2026) | Fork source for bull/bear debate structure + analyst-desk roles | Fork for *prompts + role structure*, not its LangGraph runtime — re-express roles as Claude Agent SDK subagents. [repo](https://github.com/tauricresearch/tradingagents) · **HIGH** |
| **quantstats** | latest | Performance tearsheets: Sharpe, Sortino, returns, drawdown, attribution | Compute weekly metrics off the internal sim ledger. Avoids vectorbt's `freq` footgun. **MEDIUM** (verify maintenance) |
| **empyrical-reloaded** | latest | Pure metric functions (Sharpe/Sortino/alpha/beta) if you want just the math | Alternative to quantstats for lean metric calc; maintained fork of Quantopian empyrical. **MEDIUM** (verify) |
| **Polygon.io Options** | Options Starter+ | Options-implied move / IV / greeks for the ~20 names | Only if IV/implied-move becomes a hard DD input. Polygon computes IV (binomial model). [Polygon options](https://polygon.io/options) · **MEDIUM** |
| **FINRA short-interest bulk files** | n/a (free download) | Authoritative bi-monthly short interest | Primary short-interest source; FMP short-interest as convenience layer. **MEDIUM** (verify FMP SI endpoint exists on tier) |
| **httpx** | latest | Async HTTP client for all data-provider calls | Standard for FastAPI-era async Python. **HIGH** |
| **pydantic** | v2.x | Schema/validation for agent structured outputs + ledger records | Pairs with Claude Agent SDK JSON-Schema outputs; enforce money-path invariants at trust boundaries. **HIGH** |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| `.claude/agents/*.md` subagent defs | Shared analyst-desk role definitions | Same files usable interactively (Claude Code) and programmatically (SDK). |
| Tailscale | Private transport Mac host ⇄ iPhone | Already in the user's fleet; no public exposure of the trading host. |
| launchd / cron | Schedule the catalyst T-2 scan | Triggers the SDK pipeline headless. |
| `.env` + Keychain | Data-provider API keys + RH OAuth token | Never hardcode; env-first (per user's standing rule). |
## Installation
# Agent runtime + data
# Knowledge base (embedded)
# Metrics on the sim ledger
# Optional escalations (only if needed)
# pip install polygon-api-client      # options IV / implied move
# pip install kuzu                     # ONLY the Vela-Engineering fork — see KB decision
# Robinhood: no pip install — connect the official MCP by URL in the SDK/CC MCP config
# ClinicalTrials.gov: no SDK needed — plain REST via httpx
## The Knowledge-Base decision (was: "lean Kùzu")
- **Kùzu Inc. was acquired by Apple (deal Oct 9, 2025); the original repo was archived and the company site shut down.** ([BetaKit](https://betakit.com/apple-strikes-deal-to-acquire-canadian-database-software-startup-kuzu/), [9to5Mac](https://9to5mac.com/2026/02/11/kuzu-database-company-joins-apples-list-of-recent-acquisitions/)). The only living line is a community fork, `Vela-Engineering/kuzu` (MIT). Betting a real-money system's memory layer on an acquired-and-archived core with a single third-party maintainer is avoidable risk.
- **The actual query pattern is analog/similarity search** ("similar past scenarios"), which is vector search, plus relational provenance/citations. Neither needs multi-hop Cypher traversal for a single-user, ~20-ticker, hundreds-of-records dataset.
- SQLite + sqlite-vec delivers both in one zero-ops embedded file, trivially accessible from Python, with provenance as ordinary rows. (Caveat: sqlite-vec has **no ANN index** as of early 2026 — brute-force only — which is *fine* at this scale, milliseconds.)
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Official Robinhood MCP | `robin_stocks` (unofficial) | **Never** for execution. Only conceivable use: read-only historical pulls in the paper phase — but even that risks the account; prefer FMP/yfinance for history instead. |
| FMP (fundamentals) | Alpha Vantage | If you specifically need OPRA/CBOE-licensed options + VIX family in one vendor. Alpha Vantage has strong options/IV licensing. |
| FMP + Polygon | Tiingo | Cheaper EOD + fundamentals if intraday/options depth isn't needed. |
| SQLite + sqlite-vec | Kùzu (Vela fork) | Real multi-hop analog graph traversal emerges as a core query. |
| SQLite + sqlite-vec | DuckDB + VSS | KB becomes analytics/OLAP-heavy and needs HNSW at scale. |
| Custom sim ledger + quantstats | vectorbt | You later want to sweep thousands of parameter combos. Overkill for a weekly 20-name book, and its `freq` default silently corrupts Sharpe/Sortino if unset. |
| Custom sim ledger + quantstats | backtrader | Event-driven bar-by-bar simulation with complex order types. Heavier, thinner maintenance; unnecessary for weekly holds. |
| Claude Agent SDK | Interactive Claude Code + Task tool | Manual/exploratory runs. But scheduled catalyst triggers need the headless SDK. Use both: shared `.claude/agents/` defs. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `robin_stocks` / `pyrh` / community Robinhood MCPs for **execution** | Unofficial private-endpoint APIs; "may be withdrawn at any time"; no order guardrails; account-ban / ToS risk on real money | Official Robinhood Agentic Trading MCP |
| **yfinance** as a critical data source | Wraps undocumented Yahoo endpoints; frequent 429s/breakage; ToS prohibits automated access (low enforcement for personal use, but no SLA/accuracy guarantee) | FMP / Polygon for anything that touches trade decisions; yfinance only for throwaway paper-phase delayed quotes |
| **Kùzu (original `kuzudb/kuzu`)** | Repo archived after Apple acquisition; unmaintained upstream | SQLite + sqlite-vec (default) or Vela-Engineering/kuzu fork (escalation) |
| **Neo4j server** | Operational overhead (JVM, server process, backups) for a single-user local system | Embedded SQLite/sqlite-vec |
| **vectorbt** for the paper ledger | Vectorized param-sweep engine; wrong tool for a small weekly discretionary book; silent Sharpe corruption if `freq` unset | Custom ledger + quantstats |
| Screen-scraping BioPharmaCatalyst/RTTNews as the primary catalyst feed | Fragile, ToS-gray, no SLA | ClinicalTrials.gov v2 (trials) + FMP earnings calendar + curated manual PDUFA entry (see catalyst note) |
## Catalyst-data note (Requirement: flag catalysts 1–2 days out)
- **Trial readouts:** ClinicalTrials.gov API v2 (`primaryCompletionDate`, phase, status) — authoritative, free. **HIGH**
- **Earnings dates:** FMP earnings calendar endpoint. **MEDIUM-HIGH**
- **PDUFA / AdCom dates:** aggregated by commercial trackers (BiopharmaWatch, BPIQ, MarketBeat FDA calendar, FDA Tracker). No clean free API; most are scrape-or-subscribe. **Recommendation:** for a curated ~20-name universe, treat PDUFA/AdCom as a **manually-maintained table** (the project already specifies "manual ad-hoc catalyst injection"), optionally seeded from a paid tracker (BPIQ) if budget allows. Auto-derive trial + earnings; hand-curate PDUFA. This is honest given the data landscape. **MEDIUM**
- Conference calendars (ASCO/ESMO/AHA): published schedules, best handled as manual/annual seed entries. **LOW** (no API)
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| claude-agent-sdk | Python ≥ 3.10 | Required floor. |
| sqlite-vec | SQLite with extension loading enabled | Ensure the Python `sqlite3` build (or `pysqlite3-binary`) allows `enable_load_extension`. macOS system Python often disables it. |
| Swift Charts | iOS 16+ (17+ recommended) | Set deployment target accordingly. |
| Robinhood MCP OAuth | localhost redirect only | Fine for local Mac host; would break a hosted HTTPS deployment. |
## Must Verify Before Building (open, real-money-critical)
## Sources
- [Robinhood — "Now Open to Agents" newsroom](https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/) — official MCP launch, equities-only beta, segregated account · HIGH
- [Robinhood agentic-trading product page](https://robinhood.com/us/en/agentic-trading/) — connect-by-URL, per-trade notifications, disconnect · HIGH
- [Austin Starks review of RH agentic MCP](https://medium.com/@austin-starks/i-just-tried-robinhoods-alleged-agentic-trading-i-am-not-impressed-33d3725a23e0) — actual tool list, no paper mode, localhost-only OAuth · MEDIUM
- [robin_stocks repo](https://github.com/jmfernandes/robin_stocks) + [AlgoTrading101 guide](https://algotrading101.com/learn/robinhood-api-guide/) — unofficial-API risk · HIGH
- [ClinicalTrials.gov API v2 (NLM bulletin)](https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html) — free REST/JSON, v2.0 · HIGH
- [FMP docs](https://site.financialmodelingprep.com/developer/docs) + [pricing](https://site.financialmodelingprep.com/pricing-plans) — fundamentals/float/cashflow, tiers · MEDIUM-HIGH
- [Polygon options](https://polygon.io/options) + [IV article](https://polygon.io/knowledge-base/article/what-is-implied-volatility-iv) — options/IV · MEDIUM
- [Kùzu→Apple acquisition (BetaKit)](https://betakit.com/apple-strikes-deal-to-acquire-canadian-database-software-startup-kuzu/), [9to5Mac](https://9to5mac.com/2026/02/11/kuzu-database-company-joins-apples-list-of-recent-acquisitions/), [Vela fork](https://github.com/Vela-Engineering/kuzu) — archived upstream, fork status · HIGH
- [sqlite-vec](https://github.com/asg017/sqlite-vec) + [perf comparison](https://zenn.dev/mima_ita/articles/860681ad19ea2d?locale=en) — embedded vector search, no-ANN caveat · MEDIUM
- [Claude Agent SDK production guide](https://inference.net/content/claude-agent-sdk-production-guide/) — subagents, structured outputs, no-nested-subagents constraint · HIGH (features)
- [TradingAgents repo](https://github.com/tauricresearch/tradingagents) + [arXiv 2412.20138](https://arxiv.org/html/2412.20138v5) — bull/bear debate desk, v0.2.0 · HIGH
- [vectorbt](https://github.com/polakowo/vectorbt) + [Backtrader/vectorbt comparison](https://pineify.app/resources/blog/backtrader-vs-vectorbt-vs-pineify-python-trading-framework-comparison-guide) — freq footgun, when-to-use · MEDIUM
- [yfinance ToS/reliability](https://scrapfly.io/blog/posts/guide-to-yahoo-finance-api) + [why yfinance gets blocked](https://medium.com/@trading.dude/why-yfinance-keeps-getting-blocked-and-what-to-use-instead-92d84bb2cc01) · MEDIUM
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
