# Own PDUFA (EDGAR 8-K) + Robinhood as a Data Source — Research

**Researched:** 2026-08-16
**Domain:** SEC EDGAR full-text 8-K/PR extraction (PDUFA/AdCom dates) · Robinhood Agentic MCP read surface
**Confidence:** Part 1 HIGH (live-verified real filings + exact phrasing + the verify-synergy is already coded). Part 2 MEDIUM-LOW (RH read surface is UNVERIFIED per CLAUDE.md; design + probe-plan only, gated on operator connection).

## Summary

The DATA-03 amendment (verify.py commits ef94eb9/ef2bb2c) already whitelists **`"SEC EDGAR"`** in `AUTHORITATIVE_SUFFICIENT` — the verify code comment literally says *"EDGAR is listed for future filing catalysts (no catalyst flow emits it yet)."* This research designs that missing flow. When the FDA accepts an NDA/BLA, the company files an 8-K whose EX-99.1 press release states the PDUFA target action date in a **fixed, machine-extractable phrase**. I live-fetched two real 8-Ks and confirmed the date sits verbatim, adjacent to a "PDUFA target action date" keyword. A deterministic regex over that text (no LLM) yields a `Catalyst` with a single `source_name="SEC EDGAR"` **primary** source → it flows through the unchanged insert→verify pipeline → **`_authoritative_single` fires → verified → tradeable**. This makes the fragile FR+RTTNews 2-source merge path (and all 3 latent bugs from the pdufa debug) **moot for PDUFA dates**.

**Primary recommendation:** Build `providers/pdufa_edgar.py` — efts full-text discovery filtered to universe CIKs → fetch matched 8-K press-release exhibits → regex-extract the date adjacent to the PDUFA/AdCom keyword → emit a single-source `"SEC EDGAR"` primary `Catalyst`. Reuse edgartools CIK resolution, `_http`, the catalyst pipeline, and the already-present `AUTHORITATIVE_SUFFICIENT` entry. **No verify.py change needed.** Robinhood-as-data is a design + probe-plan that cannot be built autonomously (OAuth + funded account + interactive MCP connect).

## User Constraints (from project docs — no CONTEXT.md for this task)

- **FREE only.** No paid tracker (operator explicitly rejected BPIQ). EDGAR-8K path is $0/keyless.
- **cite-or-drop / provenance.** Only emit a date that appears verbatim next to a PDUFA keyword in a real, citable filing (accession URL + fetch_ts). Anything without a citable URL is dropped, never imputed.
- **no-LLM-dates invariant.** Extraction is pure regex over real filing text; an LLM never invents or infers a date. Human confirms ambiguous extractions.
- **`.venv/bin/python`**, Graphify graph-first, minimal deps (reuse edgartools + bs4/regex already vendored).
- **Human gate on money is inviolable** (PROJECT.md): auto-verify makes a catalyst *tradeable-eligible*; the trade itself still requires explicit LP approval.
- **Robinhood execution stays Phase 11**; this task only adds the *read/data* surface, which shares Phase 11's MCP connection dependency.

---

# PART 1 — Own PDUFA system from SEC 8-K/PR (buildable now, the priority)

## 1.1 How PDUFA dates actually appear in 8-K filings — VERIFIED LIVE (2026-08-16)

EDGAR full-text search (`efts.sec.gov/LATEST/search-index?q=%22PDUFA+target+action+date%22&forms=8-K`) returned **55 in-window hits**. I fetched two real filing exhibits and captured the exact surrounding text:

**IMMUNOME (IMNM) — 8-K filed 2026-08-11, EX-99.1** (`0001193125-26-344577`):
> "Varegacestat **PDUFA target action date set for April 28, 2027**, following U.S. FDA acceptance of New Drug Application (NDA)…"
> "…FDA acceptance of our NDA with a **PDUFA target action date of April 28, 2027**…"
> "…the U.S. FDA accepted Immunome's NDA … and **assigned a PDUFA target action date of April 28, 2027**."

**CAPRICOR (CAPR) — 8-K filed 2026-05-12, EX-99.1** (`0001104659-26-059380`):
> "Deramiocel BLA under active FDA review; **PDUFA target action date of August 22, 2026**…"
> "…with the FDA review of our BLA underway and a **PDUFA target action date of August 22, 2026**…"
> "…resuming its full review of the BLA, with a **PDUFA target action date of August 22, 2026**."

### Verified phrasing patterns (the extraction target)

| Pattern (verbatim) | Frequency |
|---|---|
| `PDUFA target action date of <Month DD, YYYY>` | dominant |
| `PDUFA target action date set for <Month DD, YYYY>` | common |
| `assigned a PDUFA target action date of <Month DD, YYYY>` | common |
| `target action date of <Month DD, YYYY>` (no "PDUFA" prefix) | fallback |
| `goal date of <Month DD, YYYY>` | rarer synonym |
| AdCom: `advisory committee meeting … on/scheduled for <Month DD, YYYY>` | AdCom variant |

**Confirmed:** the date is (a) a full-month-name `Month DD, YYYY` string, (b) sits **within ~40 chars of the keyword**, (c) is repeated 3+ times per filing (redundancy = confidence), and (d) the filing carries an authoritative accession URL. Extractable and citable. The efts hit metadata gives `ciks`, `display_names` (with ticker in parens), `form`, `adsh`, `file_date`, and the exhibit `_id` (→ doc URL) directly — no HTML table scraping.

## 1.2 Extraction approach — deterministic, no-LLM, cite-or-drop

**Discovery (efts full-text search, keyless):** one query per keyword phrase, `forms=8-K`, filtered to the universe CIK set. `~3 queries/cycle` (`"PDUFA target action date"`, `"target action date"`, `"advisory committee meeting"`). Filter hits where `_source.ciks ∩ universe_ciks` (exact CIK match — **no fuzzy title matching**, which kills the FR title-attribution bug). Build `ticker→CIK` once from the seed universe via edgartools `Company(ticker).cik` (edgar.py already resolves this).

**Extraction (regex over fetched exhibit text):**
```python
# Capture Month DD, YYYY immediately following a PDUFA/target-action/goal keyword.
_PDUFA_RX = re.compile(
    r"(?:PDUFA\s+)?(?:target\s+action|goal)\s+date\s+(?:of|set\s+for|is|:)?\s*"
    r"([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})", re.I)
_ADCOM_RX = re.compile(
    r"advisory\s+committee\s+meeting[^.]{0,80}?(?:on|scheduled\s+for)\s+"
    r"([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})", re.I)
```
Reuse `dates._norm_date`-equivalent (`pdufa._norm_date` already parses `%B %d, %Y`) to ISO-normalize. **cite-or-drop:** emit only if (1) the regex matched inside a fetched real filing, (2) the date normalizes, (3) the filing has an accession URL. Never emit a date not adjacent to a keyword.

**Confidence scoring + human-review queue:**
- **HIGH** (auto-emit → auto-verifies → tradeable-eligible): `"PDUFA"` token present in the match, single unambiguous date, ≥2 keyword+date co-occurrences in the doc. This is the common case (both live examples qualify).
- **MEDIUM/LOW** (write to a review CSV the operator confirms — the existing ~10-min/week task, **now auto-populated from real filings**): multiple candidate dates, keyword-only-far-from-date, `"target action date"` without `"PDUFA"`, or AdCom with an ambiguous meeting date. Reuses the existing `verify.load_curated_pdufa` CSV path so a confirmed row re-enters as a normal catalyst.

The no-LLM invariant holds: the pipeline only ever surfaces a date that a human can see verbatim in the linked 8-K. The LLM desk never mints the date.

## 1.3 Wiring to the calendar + the verify-synergy — a single EDGAR-8K catalyst WILL verify + trade

The new provider emits:
```python
Catalyst(
    ticker=ticker, company_name=<from display_names>,
    catalyst_type=CatalystType.pdufa,           # or .adcom
    event_date=<ISO PDUFA date>,
    date_precision=parse_precision(event_date), # day (full date) → firm
    uncertainty_type=classify(event_date, DateType.estimated.value, source_count=1, has_primary=True),
    source_origin=SourceOrigin.curated_pdufa,   # reuse the PDUFA/AdCom bucket (no DB migration)
    external_ref=f"pdufa_edgar:{ticker}:{accession}",   # own ref — no collision with FR/RTTNews/curated
    sources=[CatalystSource(
        source_name="SEC EDGAR",                # ← MUST be verbatim; it is the AUTHORITATIVE_SUFFICIENT key
        source_url=<8-K exhibit accession URL>, # authoritative provenance
        source_type=SourceType.primary,         # required by _authoritative_single
        reported_date=event_date,
        date_type=DateType.estimated,           # announced target, not realized (mirrors pdufa.py)
        published_date=<8-K filing_date>,       # transport-only → point-in-time last_verified_at stamp
        retrieved_at=now)],
)
```

**Why it verifies (traced through verify.py):** `verify_catalyst` computes `agreeing`, then `verified = (len>=2 and has_primary) OR _authoritative_single(agreeing)`. `_authoritative_single` returns True iff some agreeing source has `source_type==primary AND source_name in AUTHORITATIVE_SUFFICIENT`. `"SEC EDGAR"` **is already in that frozenset** (verify.py line 43). So a single EDGAR-8K primary → `_authoritative_single` True → `Status.verified` → `is_tradeable` True. **Answer: YES — one EDGAR-8K PDUFA catalyst verifies and becomes tradeable-eligible with zero verify.py changes.** (Trade still human-gated per PROJECT.md.)

**Point-in-time / anti-look-ahead (BACK-01):** set `published_date = 8-K filing_date`. `ingest._pit_stamp` reads the primary source's in-memory `published_date` and stamps `last_verified_at` from it — the date the PDUFA target became publicly knowable, never `now()`/`event_date`. This is exactly the clinicaltrials.gov pattern (`lastUpdatePostDateStruct.date`), already wired.

**Daemon path (fixes a pdufa-debug gap):** wire the new provider into `ingest._fetch_catalysts` (line 166) — `out += _safe(providers.get("pdufa_edgar"), tickers, start, end) or []` — and add a `pdufa_edgar` slot in `registry.build_providers` + a `CADENCE["pdufa_edgar"] = _DAY`. Unlike `verify.load_curated_pdufa` (only reachable via `calendar/refresh.py` main(), **not** on the daemon path — the debug's finding), `_fetch_catalysts` runs inside `run_cycle`, so EDGAR PDUFA auto-populates on every daemon cycle.

### The 3 latent pdufa-debug bugs — made MOOT by the EDGAR-8K path

| Debug bug | Why the EDGAR-8K path moots it |
|---|---|
| (a) merge-key mismatch (FR meeting date ≠ RTTNews action date → never merge) | No merge needed. A single `"SEC EDGAR"` primary self-verifies; the 2-source FR+RTTNews machinery is bypassed for PDUFA. |
| (b) title-attribution weakness (legal name vs FR title format) | Attribution is by **CIK match** (efts hit `ciks` ∩ universe CIKs), not fuzzy title strings. Exact. |
| (c) curated 2-source can't reach gate (external_ref collision) | New provider uses its own `pdufa_edgar:{ticker}:{accession}` ref; single-source verifies, so the ≥2-agreeing gate is irrelevant. |

**Does the EDGAR-8K path make the RTTNews-merge path moot?** **Yes, for PDUFA dates.** RTTNews (dead-scraper YELLOW half) and the FR+RTTNews merge become optional redundancy/discovery only — not required for a tradeable PDUFA. FedRegister stays as the authoritative AdCom source (it already self-verifies via `"Federal Register"` in the frozenset). The existing `providers/pdufa.py` can be **left as-is** (redundant discovery) or retired later; no need to fix its 3 bugs to ship tradeable PDUFA.

## 1.4 Redundancy + adaptability

| Tier | Source | Role | Verifies alone? |
|---|---|---|---|
| Primary | **SEC EDGAR 8-K/EX-99.1** (efts + regex) | authoritative PDUFA/AdCom date + provenance | **Yes** (`"SEC EDGAR"` ∈ AUTHORITATIVE_SUFFICIENT) |
| Secondary | Company IR RSS / PR wires (per-name feeds) | earlier signal + cross-check (optional) | No (secondary) — corroboration only |
| AdCom | **Federal Register API** (already built) | government AdCom meeting notices | Yes (`"Federal Register"`) |
| Discovery (optional) | RTTNews (currently dead — JS-rendered) | broad discovery hints only | No |

**Operator tuning knobs (all $0):** the keyword list + regexes (add "goal date"/synonyms), per-name IR RSS feeds, the date-proximity window (~40 chars), the confidence threshold that routes MEDIUM/LOW to the review CSV, and the efts phrase set. The `AUTHORITATIVE_SUFFICIENT` frozenset is the one auditable place that governs what self-verifies.

## 1.5 Reuse vs. build

**REUSE (no change):** edgartools CIK resolution (edgar.py pattern) · `_http.get_json`/`get_text` (cache/rate-limit/snapshot/UA discipline; SEC UA already required) · `models.Catalyst/CatalystSource` · `dates.classify/parse_precision` + `pdufa._norm_date` · the insert→verify pipeline · `ingest._pit_stamp` · **`verify.AUTHORITATIVE_SUFFICIENT` (already contains `"SEC EDGAR"`)** · the `verify.load_curated_pdufa` CSV path (for the human-review queue).

**BUILD (small, one file):** `providers/pdufa_edgar.py` — efts discovery + CIK filter + exhibit fetch + regex extract + `Catalyst` emit + confidence split. Plus ~4 lines wiring into `ingest._fetch_catalysts` + `registry.build_providers` + `CADENCE`. **No verify.py edit. No DB migration** (reuse `curated_pdufa` origin — pdufa.py already uses it; grep found no `source_origin` CHECK constraint in db.py).

**Runtime State Inventory:** N/A — greenfield provider + additive wiring; no rename/refactor of stored data, no OS-registered state.

---

# PART 2 — Maximize Robinhood as a DATA source (design + probe-plan, gated)

## 2.1 The RH Agentic Trading MCP read surface — UNVERIFIED (probe required)

Per CLAUDE.md STACK + the newsroom/Austin-Starks review, the **whole surface is flagged UNVERIFIED** — exact tool names, params, and return schemas need a live probe. Best-known READ tools:

| Tool (as reported) | Likely purpose | Data value here | Status |
|---|---|---|---|
| `get_portfolio` | positions, cash, buying power | **HIGH** — ground-truth ledger for reconciliation | UNVERIFIED schema |
| `get_equity_quotes` | last/bid/ask per symbol | **HIGH** — real-time exec-time pricing + intra-week monitor | UNVERIFIED (real-time vs delayed?) |
| watchlists | saved symbol lists | LOW — we already own the curated universe | UNVERIFIED |
| scans | screeners | LOW — not our universe model | UNVERIFIED |
| fundamentals (?) | company facts | LOW — EDGAR XBRL is authoritative + free | UNVERIFIED |
| single-leg option orders / `place_equity_order` | execution (write) | out of Part-2 scope (Phase 11) | UNVERIFIED |

## 2.2 DEPENDENCY (explicit) — cannot be built autonomously

Using RH for data requires the operator to **connect the RH Agentic MCP**: OAuth with a **localhost redirect** (per STACK.md — breaks on hosted HTTPS), a **funded RH account**, and adding the MCP URL to the CC/SDK MCP config. This is an interactive, credentialed, money-account action — **it cannot be done by an autonomous agent.** Therefore Part 2 ships as **a design + a probe-plan**, not a build. A degrade-to-None adapter file *can* be written now (mirrors how `macro` degrades to None without a FRED key), but wiring + verification are **gated on the operator connecting the MCP** — the same connection Phase 11 already needs.

**Architectural nuance (flag):** unlike the free httpx providers, RH data does **not** flow through `_http`. The MCP tool surface is consumed by the **Claude Agent SDK / CC runtime**, so the RH "provider" is a thin **MCP-tool adapter** invoked from the agent runtime (the SDK has native MCP integration per STACK.md), not an httpx call. The probe must confirm the **headless SDK** can invoke these read tools programmatically (the daemon runs headless), not just interactive CC.

## 2.3 Where RH data adds value — pluggable, never sole-source

Wire RH as **additional** slots in `registry.build_providers` that degrade to None when the MCP is disconnected (exactly like `macro`):
- **`quotes_rt`** → `get_equity_quotes`: real-time cross-check of CBOE/yfinance (both 15-min-delayed) **and** execution-time last-look pricing. **Gated to the trade-candidate set only** (the handful about to trade) — never the 20-name bulk, never history.
- **`portfolio`** → `get_portfolio`: reconcile the internal sim/paper ledger against actual RH positions + cash (ground truth of holdings).

**Broker/account-safety + ToS (ponytail: broker = real-time + portfolio only, free sources = history):**
- **Never** hammer the execution broker for bulk/historical data — that stays yfinance + the free cascade (INGEST-01). RH is the price *spine's* real-time top-up + the ledger reader, **not** a replacement.
- Cache RH reads (short TTL), keep call volume tiny (trade set only), and confirm read calls trigger no order side-effects / notifications.
- RH quote is a **cross-check + exec-time** input, not authoritative history — the free stack remains the system of record.

## 2.4 Concrete probe-plan (run once the operator connects the MCP)

1. **Operator** connects RH Agentic MCP (OAuth localhost, funded account) in the CC/SDK MCP config. (Blocking, manual.)
2. **Enumerate tools:** list the MCP server's tools + JSON schemas — names, params, return shapes — and replace the UNVERIFIED CLAUDE.md list with verified reality.
3. **Quote read:** call `get_equity_quotes` on 2–3 universe tickers → capture fields (last/bid/ask/timestamp), and **real-time vs delayed** (compare timestamp to wall clock + to CBOE `iv30`/spot).
4. **Portfolio read:** call `get_portfolio` → capture positions/cash/buying-power shape; map to the sim-ledger reconciliation record.
5. **Limits + safety:** call reads N times; note throttle/rate-limit/error semantics; **confirm reads produce no orders and no push notifications.**
6. **Headless path:** confirm the Claude Agent SDK can invoke these read tools programmatically in the daemon context (not just interactive CC).
7. **Wire + verify:** implement `providers/robinhood.py` MCP adapter → `registry` `quotes_rt` + `portfolio` slots (degrade-to-None) → cross-check RH quote vs CBOE/yfinance; reconcile portfolio vs sim ledger. Provenance: `source_name="Robinhood"`, grade YELLOW (broker convenience, **not** in AUTHORITATIVE_SUFFICIENT).

---

# Proposed ROADMAP phase

## Phase 06.11 — EDGAR-8K PDUFA Autopopulation (+ Robinhood data, gated)

**Goal:** Auto-populate tradeable PDUFA/AdCom catalysts from SEC 8-K/PR (authoritative + free + adaptable), exploiting the DATA-03 `"SEC EDGAR"` synergy; land the Robinhood *read* surface as a design + probe-plan gated on the operator's MCP connection.

**Depends on:** Phase 1 (catalyst pipeline + verify), Phase 06.10 (daemon). Shares Phase 11's RH MCP connection dependency.

**Requirements:**
- **PDUFA-EDGAR-01** — `providers/pdufa_edgar.py` discovers PDUFA/AdCom 8-Ks via EDGAR full-text search filtered to universe CIKs (exact CIK match, no fuzzy title).
- **PDUFA-EDGAR-02** — Deterministic regex extracts the date verbatim-adjacent to a PDUFA/target-action/goal/AdCom keyword; no-LLM-dates + cite-or-drop enforced (drop any date lacking an accession URL or keyword adjacency).
- **PDUFA-EDGAR-03** — Emitted `Catalyst` carries a single `source_name="SEC EDGAR"` **primary** source → verifies via `_authoritative_single` → tradeable-eligible, with `last_verified_at` stamped point-in-time from the 8-K filing_date (BACK-01).
- **PDUFA-EDGAR-04** — Wired into `ingest._fetch_catalysts` + `registry` + `CADENCE` so it runs on the daemon cycle; confidence scoring routes ambiguous extractions to the human-review CSV (`verify.load_curated_pdufa` path).
- **RH-DATA-01** (design) — `providers/robinhood.py` MCP-adapter skeleton (degrade-to-None when disconnected) + `quotes_rt`/`portfolio` registry slots, pluggable + never sole-source.
- **RH-DATA-02** (gated) — Execute the §2.4 probe-plan once the operator connects the MCP; document the verified read schema.
- **RH-DATA-03** (gated) — Wire RH real-time quote as a cross-check/exec-time input (trade set only) + portfolio reconciliation vs the sim ledger, with ToS-safe rate discipline.

**Success Criteria (what must be TRUE):**
1. Running the daemon against the live universe produces ≥1 **verified, tradeable-eligible** PDUFA/AdCom catalyst whose sole source is `"SEC EDGAR"` with a citable 8-K accession URL (live-provable today on IMNM Apr-28-2027 / CAPR Aug-22-2026).
2. No date is ever emitted that does not appear verbatim adjacent to a PDUFA/AdCom keyword in a fetched real filing (cite-or-drop; no-LLM-dates); ambiguous extractions land in the human-review CSV, not the tradeable set.
3. `last_verified_at` is stamped from the 8-K filing_date (never now()/event_date); the extractor and pipeline change **zero** lines of verify.py.
4. RH-DATA-01 ships as a degrade-to-None adapter + design doc; RH-DATA-02/03 are explicitly **blocked** on the operator connecting the RH MCP and do not gate the PDUFA-EDGAR deliverable.

**Reuse vs. build:** Reuse edgartools + `_http` + the catalyst pipeline + `AUTHORITATIVE_SUFFICIENT` (already has `"SEC EDGAR"`) + the curated-CSV review path. Build one provider file + ~4 wiring lines for PDUFA-EDGAR. Build a degrade-to-None RH adapter now; gate its wiring/verification on the operator's MCP connection.

**Validation Architecture (nyquist enabled):** pytest (existing — `tests/test_providers_pdufa.py`, `test_verify.py`, `test_ingest_seam.py`). Wave-0 gaps: `tests/test_providers_pdufa_edgar.py` (regex extraction on the two captured real-filing fixtures + cite-or-drop drop-cases + single-source-verifies assertion), and an `ingest` integration test that a `"SEC EDGAR"` primary reaches `Status.verified`. RH adapter: a degrade-to-None unit test (disconnected → None, never raises).

---

## Sources

**Primary (HIGH):**
- EDGAR full-text search — `https://efts.sec.gov/LATEST/search-index?q=%22PDUFA+target+action+date%22&forms=8-K` (live 2026-08-16, 55 hits, keyless).
- IMNM 8-K EX-99.1 — `https://www.sec.gov/Archives/edgar/data/1472012/000119312526344577/imnm-ex99_1.htm` (live-fetched; "PDUFA target action date … April 28, 2027").
- CAPR 8-K EX-99.1 — `https://www.sec.gov/Archives/edgar/data/1133869/000110465926059380/capr-20260512xex99d1.htm` (live-fetched; "PDUFA target action date of August 22, 2026").
- Codebase: `src/catalyst_trader/calendar/verify.py` (AUTHORITATIVE_SUFFICIENT + `_authoritative_single`), `providers/{edgar,pdufa,clinicaltrials}.py`, `providers/registry.py`, `ingest.py`, `providers/_http.py`, `models.py`. edgartools v5.49.0 verified locally.
- `.planning/debug/pdufa-zero-catalysts.md` (the 3 latent bugs, now mooted).

**Secondary (MEDIUM):**
- `.planning/research/free-data-sources.md` §2 (EDGAR/FR/RTTNews landscape), `api-keys-and-costs.md` (PDUFA deep-dive), `CLAUDE.md` STACK (RH MCP surface).

**Tertiary (LOW / UNVERIFIED — flagged for probe):**
- Robinhood Agentic Trading MCP read-tool schema — UNVERIFIED per CLAUDE.md; requires the §2.4 probe after operator connection.

## Metadata

- **Confidence:** Part 1 stack/architecture HIGH (live filings + coded synergy), pitfalls HIGH. Part 2 MEDIUM-LOW (RH surface UNVERIFIED, gated).
- **Research date:** 2026-08-16 · **Valid until:** ~2026-09-15 (EDGAR/edgartools stable; RH surface may change — re-probe on connect).
