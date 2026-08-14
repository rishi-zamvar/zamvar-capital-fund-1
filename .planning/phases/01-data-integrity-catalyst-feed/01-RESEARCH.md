# Phase 1: Data Integrity & Catalyst Feed - Research

**Researched:** 2026-08-14
**Domain:** External catalyst-data ingestion + verified rolling calendar + point-in-time universe (money-critical date integrity)
**Confidence:** HIGH (ClinicalTrials.gov v2 live-verified; project conventions HIGH) · MEDIUM (FMP exact fields, PDUFA landscape) · LOW (none load-bearing)

## Summary

This phase builds the trust root of the whole system: a rolling catalyst calendar where **no date ever originates from an LLM's memory**, every date carries a two-source verification record + uncertainty type + freshness stamp, and unverifiable dates are structurally excluded from trading. The three data sources resolve cleanly: ClinicalTrials.gov API v2 (trial readouts — free, no auth, **live-verified during this research**), FMP earnings calendar (earnings — free tier 250 req/day), and a **hand-curated PDUFA/AdCom table** (confirmed: no clean free API exists anywhere). It also establishes the project's foundational conventions (src-layout Python package, `pyproject.toml`, pytest harness, httpx+pydantic provider pattern, single-file SQLite store) that all later phases inherit.

The single most important technical finding: **ClinicalTrials.gov `primaryCompletionDate` is frequently a partial date** — a live sample of Vertex trials returned `"2027-04"`, `"2032-12"` (year-month only) for ~35% of records, and the field is typed `ESTIMATED` vs `ACTUAL`. A month-only estimated completion date is inherently a *window*, not a firm date, and silently coercing it to a day (e.g. treating `2027-04` as `2027-04-01`) would be a correctness bug that in this domain is a total-loss vector. The uncertainty-typing requirement (DATA-04) is not decoration — it falls directly out of the source data's own precision, and the parser must preserve it.

**Primary recommendation:** Build a provider→verify→store pipeline where (1) every provider returns typed records with source provenance attached, (2) a `verify` module enforces the two-source rule and derives `firm`/`window`/`soft` from source precision (never from a guess), (3) a single idempotent daily `refresh` entrypoint (run via **launchd**, not an in-process scheduler) re-verifies within 48h and emits a T-2 trigger seam, and (4) a `universe` module writes append-only point-in-time snapshots including delisted names. TDD throughout, with exhaustive partial-date/freezegun edge-case suites on the money-critical date path.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use the ROADMAP phase goal, success criteria, PROJECT.md constraints, and the STACK decisions in CLAUDE.md (ClinicalTrials.gov API v2 for trial readouts, FMP earnings calendar, hand-curated PDUFA/AdCom table, httpx + pydantic, SQLite) to guide decisions.

Hard constraints from PROJECT.md that bind this phase:
- **No catalyst date may originate from an LLM's memory** — every date comes from a named external source.
- **Two-source verification** + `last_verified` stamp + uncertainty typing (firm/window/soft) on every date; unverifiable dates are flagged and **excluded from trading**.
- **Full test coverage / TDD** — tests before logic; money-critical date handling gets exhaustive edge cases.
- **Simplicity + readability**: simplest production-ready implementation, minimal dependencies.

### Claude's Discretion
Everything else — package layout, module boundaries, schema details, scheduler mechanism, seed-universe source — is Claude's discretion, guided by the constraints above.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped. (Downstream out-of-scope for this phase specifically: KB/sqlite-vec vectors — Phase 2; quant tools — Phase 3; any agent logic; any execution.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **DATA-01** | Rolling catalyst calendar (PDUFA/AdCom curated, trial readouts via CT.gov v2, conferences, earnings) for the covered universe | CT.gov v2 study-search + date-range filter (live-verified §Standard Stack); FMP earnings calendar; hand-curated PDUFA table (§Don't Hand-Roll); `catalyst` table (§Data Model) |
| **DATA-02** | User can inject an ad-hoc catalyst (ticker + type + date/window) | Same `catalyst` table, `source_origin='ad_hoc_user'`, flows through identical verify path via a CLI entrypoint (§Ad-hoc Injection) |
| **DATA-03** | Every date two-source verified + re-verified 48h before event; unverifiable flagged, never traded | `catalyst_source` provenance rows + two-source rule + `last_verified_at` + daily `refresh` via launchd + `status=excluded` (§Verification Model) |
| **DATA-04** | Dates typed point-estimate vs window, uncertainty carried downstream | `uncertainty_type` enum derived from source precision — CT.gov partial-date + ESTIMATED/ACTUAL typing is the direct signal (§Critical Pitfalls, §Verification Model) |
| **DATA-05** | Flags catalysts 1–2 days out and triggers Workflow 1 | Daily scan detects T-2/T-1 verified catalysts → writes a trigger row / calls a pluggable callback seam (Workflow 1 doesn't exist yet — build the seam only) (§Architecture Patterns) |
| **DATA-06** | Assembles + maintains ~20-name universe from criteria (catalyst density, market cap, liquidity, therapeutic area) | Append-only `universe_snapshot` (point-in-time, includes delisted), criteria from calendar + FMP fundamentals, curated seed (§Point-in-Time Universe) |
</phase_requirements>

## Standard Stack

### Core (Phase 1 runtime — all verified against PyPI 2026-08-14)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **httpx** | 0.28.1 | Async/sync HTTP client for all provider calls | Project-locked in CLAUDE.md; standard modern Python HTTP; sync `Client` is enough for a once-daily batch job (no async needed at this scale). **HIGH** |
| **pydantic** | 2.13.4 | Typed models + trust-boundary validation for every ingested record and DB row | Project-locked; enforces money-path invariants (e.g. "no catalyst without ≥1 source row") at parse time. **HIGH** |
| **pydantic-settings** | 2.x (ships with pydantic v2) | Env-first config for API keys (FMP) + paths | Enforces the env-first secrets rule; no hardcoded keys. **HIGH** |
| **sqlite3** (stdlib) | Python 3.14 / SQLite 3.53.3 | The catalyst + universe store | Stdlib — zero dependency. `enable_load_extension` **is available** (verified) so Phase 2's sqlite-vec will load cleanly on this same DB file. **HIGH** |

### Supporting (dev/test)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pytest** | 9.1.1 | Test harness | All tests. **HIGH** |
| **pytest-httpx** | 0.36.2 | Mock httpx responses with recorded fixtures | Provider unit tests — never hit live APIs in CI (deterministic, offline). Pairs natively with httpx. **HIGH** |
| **freezegun** | 1.5.5 | Freeze/travel `now()` in tests | The 48h-re-verify and T-2-trigger logic is time-dependent — freezegun makes those boundaries testable deterministically. **HIGH** |
| **coverage** (via pytest-cov) | latest | Coverage gate for the TDD requirement | OPS-04 full-coverage constraint. **MEDIUM** |
| **ruff** | latest | Lint + format | Single fast tool for the "readable" constraint. Optional but recommended. **MEDIUM** |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| launchd (daily scan) | APScheduler (in-process) | APScheduler needs an always-on process; for a once-daily idempotent job launchd is less code + survives reboots. Use APScheduler only if sub-daily cadence is ever needed (it isn't — one-week holds, T-2 window). |
| pytest-httpx | respx (0.23.1) | Both mock httpx; pytest-httpx is a pytest-native fixture (less boilerplate). Either works — pick pytest-httpx. |
| Hand-rolled SQL migrations | Alembic | Alembic is ORM-migration machinery for a schema this small it's overkill. A `migrations/NNN_*.sql` dir + a `schema_version` row is ~20 lines and carries cleanly into Phase 2. |
| pydantic-settings | python-dotenv + os.environ | pydantic-settings gives typed, validated config in one model; dotenv is lower-level. Marginal — either is fine. |

**Installation:**
```bash
pip install httpx pydantic pydantic-settings
pip install --group dev pytest pytest-httpx freezegun pytest-cov ruff   # or [project.optional-dependencies].dev
```

**Version note:** Runtime env is **Python 3.14.6 / SQLite 3.53.3** (verified). All Phase-1 deps support 3.14. `sqlite-vec` (0.1.9) and `claude-agent-sdk` (0.2.138) are **Phase 2+ deps, not needed here** — do not install them in this phase. `enable_load_extension` is available on this interpreter, so the Phase-2 vector extension will attach to the same DB file with no interpreter swap.

## ClinicalTrials.gov API v2 — Live-Verified Reference

**All of the below was verified by live calls during this research (2026-08-14), API version `2.0.5`, `dataTimestamp` refreshes daily ~09:00 UTC.** Confidence: **HIGH**.

**Base:** `https://clinicaltrials.gov/api/v2` · free · no auth · REST/JSON.

**Main endpoint:** `GET /studies`

**Query parameters that matter here:**
| Param | Example | Purpose |
|-------|---------|---------|
| `query.spons` | `Vertex Pharmaceuticals Incorporated` | Sponsor/collaborator search (Essie syntax) |
| `query.cond` | `Cystic Fibrosis` | Condition/therapeutic-area filter (for universe criteria) |
| `filter.overallStatus` | `RECRUITING\|ACTIVE_NOT_RECRUITING` (pipe = OR, URL-encode `%7C`) | Status filter — verified working |
| `filter.advanced` | `AREA[PrimaryCompletionDate]RANGE[2026-08-14,2026-12-31]` | **Date-window query — verified working. This is the core "what readouts are coming" query.** |
| `fields` | `NCTId,BriefTitle,Phase,OverallStatus,PrimaryCompletionDate,LeadSponsorName` | Field projection (request PascalCase names) |
| `pageSize` | `100` (max ~1000) | Page size |
| `pageToken` | (opaque) | Pagination — response returns `nextPageToken` until exhausted |
| `countTotal` | `true` | Include `totalCount` in response |

**Exact response field paths** (nested, camelCase — differs from the `fields` request names):
```
protocolSection.identificationModule.nctId              # "NCT05915442"
protocolSection.identificationModule.briefTitle
protocolSection.statusModule.overallStatus              # "RECRUITING" | "ACTIVE_NOT_RECRUITING" | ...
protocolSection.statusModule.primaryCompletionDateStruct.date   # "2027-11-14"  OR  "2027-04"  (PARTIAL!)
protocolSection.statusModule.primaryCompletionDateStruct.type   # "ESTIMATED" | "ACTUAL"
protocolSection.sponsorCollaboratorsModule.leadSponsor.name     # "Vertex Pharmaceuticals Incorporated"
protocolSection.designModule.phases                     # ["PHASE3"]  (list; may be absent)
```

**⚠️ Three verified gotchas that shape the data model:**
1. **Partial dates are common.** Live sample: `"2027-04"`, `"2032-12"` — ~7 of 20 records were year-month only. `primaryCompletionDateStruct.date` is `YYYY-MM-DD` **or** `YYYY-MM` (and occasionally `YYYY`). The parser MUST detect precision and map month-only → `window`, never coerce to a day.
2. **`type` = `ESTIMATED` vs `ACTUAL`.** An upcoming catalyst is always `ESTIMATED` (a guided estimate, not a commitment) → this is a direct input to uncertainty typing. `primaryCompletionDate` is a *guided window*, not a hard readout date — it is the best free proxy, not gospel.
3. **Sponsor mapping is fuzzy.** `query.spons=Vertex Pharmaceuticals` returned 29 studies, but some had `leadSponsor.name = "Virginia Commonwealth University"` (Vertex is only a collaborator). **You cannot map ticker→trials by loose sponsor search alone.** Requires a curated `ticker → exact legal leadSponsor name(s)` map, then filter to studies where that entity is the *lead* sponsor (or explicitly accept collaborator studies with a flag). See §Don't Hand-Roll.

**Rate limit:** No `X-RateLimit` headers are exposed (server is `istio-envoy`). Community/secondary guidance is **~50 requests/minute** with ~1.5s spacing recommended. Confidence **MEDIUM** — not officially published. At ~20 tickers polled once daily this is a non-issue; add a small sleep between requests and a retry-with-backoff wrapper anyway.

## FMP Earnings Calendar — Reference

Confidence: **MEDIUM** (endpoint + free tier confirmed via search; exact field names to confirm against a live response with the API key at build time — FMP docs return HTTP 403 to automated fetch).

- **Endpoint (stable):** `GET https://financialmodelingprep.com/stable/earnings-calendar?from=YYYY-MM-DD&to=YYYY-MM-DD&apikey=...`
- **Confirmed vs estimated:** There is a **separate "Earnings Confirmed" endpoint** distinct from the calendar. The calendar returns upcoming (estimated) + past dates; the confirmed endpoint returns only company-confirmed announcements. Use *confirmed* to promote an earnings catalyst from `window`/`soft` → `firm`.
- **Response fields (expected — verify at build):** `date`, `symbol`, `epsEstimated`, `eps`(actual), `revenueEstimated`, `revenue`(actual). `epsEstimated` may be null for thinly-covered names.
- **Free tier:** **250 API requests/day.** A once-daily calendar pull for a ~20-name universe fits easily. Bandwidth cap noted on paid tiers (Starter = 20GB/30d) is irrelevant at this volume.
- **Key key:** `FMP_API_KEY` env var (never hardcoded).

**Build-time action:** with the real key, capture one live earnings-calendar JSON and one confirmed JSON as test fixtures, and confirm the exact field names before writing the parser. Marked in Wave 0.

## PDUFA / AdCom — Confirmed No Free API

Confidence: **HIGH** on the negative claim (cross-verified: RTTNews, BPIQ, BiopharmaWatch, TheraRadar, FDATracker, Dan Sfera all reviewed — every one is a subscription or a scrapeable web calendar, none exposes a clean documented free API).

| Source | Access | Cost |
|--------|--------|------|
| BiopharmaWatch FDA/PDUFA calendar | Free **web page** (no API; scrapeable but ToS-gray, fragile, no SLA) | Free |
| RTTNews Biotech FDA Calendar | Subscription | ~$99/mo (7-day trial) |
| BPIQ PDUFA/AdCom calendar | Subscription | Paid |
| TheraRadar / FDATracker / Dan Sfera | Subscription / curated feed | Paid |

**Decision (already locked in CLAUDE.md, confirmed correct):** PDUFA/AdCom is a **hand-curated table** (`data/pdufa_curated.csv` → loaded into the `catalyst` table with `source_origin='curated_pdufa'`). This is honest given the data landscape and is *why the two-source rule matters* — a hand-typed PDUFA date is exactly the kind of entry that needs a second independent source (company IR press release / FDA) before it's tradeable. Do **not** build a scraper as the primary feed (fragile, ToS-gray, no SLA — flagged in STACK.md "What NOT to Use"). Optionally seed the curated table by hand from BiopharmaWatch's free calendar; a paid BPIQ seed is a budget decision, not a code decision.

## Architecture Patterns

### Recommended Project Structure (src-layout — establishes the project skeleton)
```
zamvar-capital-fund-1/
├── pyproject.toml                    # PEP 621; deps + [tool.pytest.ini_options] + ruff
├── src/catalyst_trader/
│   ├── __init__.py
│   ├── config.py                     # pydantic-settings: FMP_API_KEY, DB path, tunables
│   ├── db.py                         # sqlite3 connect + migration runner
│   ├── migrations/001_init.sql       # numbered .sql files, applied in order
│   ├── models.py                     # pydantic: Catalyst, CatalystSource, UniverseSnapshot, enums
│   ├── providers/
│   │   ├── base.py                   # Provider protocol → returns typed records + source metadata
│   │   ├── clinicaltrials.py         # CT.gov v2 client (partial-date-aware parse)
│   │   └── fmp.py                    # FMP earnings calendar + confirmed client
│   ├── calendar/
│   │   ├── verify.py                 # two-source rule + uncertainty typing + exclusion
│   │   ├── refresh.py                # idempotent daily entrypoint (launchd target)
│   │   └── triggers.py               # T-2 detection + pluggable trigger seam
│   ├── universe/
│   │   └── build.py                  # point-in-time snapshot builder
│   └── cli.py                        # ad-hoc injection + manual ops
├── tests/
│   ├── conftest.py                   # DB fixture (in-memory / tmp), frozen-clock fixture
│   ├── fixtures/                     # recorded CT.gov + FMP JSON
│   ├── test_dates.py                 # EXHAUSTIVE partial-date/precision suite
│   ├── test_clinicaltrials.py
│   ├── test_fmp.py
│   ├── test_verify.py                # two-source rule, exclusion, freshness
│   ├── test_triggers.py             # 48h re-verify + T-2 (freezegun)
│   └── test_universe.py              # point-in-time correctness, delisted retention
├── data/
│   ├── seed_universe.csv             # curated starting ~20 names
│   ├── ticker_sponsor_map.csv        # ticker → CT.gov legal leadSponsor name(s)
│   └── pdufa_curated.csv             # hand-curated PDUFA/AdCom
└── com.zamvar.catalyst-refresh.plist # launchd job → runs refresh.py daily
```

### Pattern 1: Provider returns records WITH provenance attached (never bare dates)
**What:** Each provider method returns typed records where every date already carries `(source_name, source_url, source_type, retrieved_at, raw_date_string, precision)`. The store layer physically cannot insert a date without a source row.
**When to use:** Every ingestion path — CT.gov, FMP, curated CSV, ad-hoc CLI.
**Why:** This is the enforcement mechanism for "no LLM-sourced date." A date exists in the DB **iff** it came from a named fetch/curation with a URL. Establishes Phase 2's provenance-enforced `:CITES` write-path pattern early.

### Pattern 2: Uncertainty type is DERIVED from source precision, never assigned by judgement
```python
# Source: derived from live-verified CT.gov primaryCompletionDateStruct shape
def classify(raw_date: str, date_type: str, source_count: int, has_primary: bool) -> Uncertainty:
    # raw_date is "YYYY-MM-DD" | "YYYY-MM" | "YYYY"
    if len(raw_date) < 10:              # month- or year-only → inherently a window
        return Uncertainty.WINDOW
    if date_type == "ESTIMATED":        # full date but company-guided estimate
        return Uncertainty.WINDOW if source_count < 2 else Uncertainty.FIRM
    if source_count >= 2 and has_primary:
        return Uncertainty.FIRM         # confirmed exact day, corroborated
    return Uncertainty.SOFT             # single-source / rumored
# ponytail: precision-driven rules, not a model. Tune thresholds if a source class misclassifies.
```
**Why:** DATA-04 is not a labelling opinion — it's a fact about how precisely the source knows the date. A month-only CT.gov date *is* a window; a two-source-corroborated PDUFA day *is* firm.

### Pattern 3: Idempotent daily refresh + T-2 trigger as a seam
**What:** `refresh.py` is a single entrypoint that (a) re-fetches sources for all active catalysts, (b) re-runs verify, (c) restamps `last_verified_at`, (d) excludes anything that can't re-verify or is stale >48h near its event, (e) detects verified catalysts 1–2 days out and fires the trigger. Safe to run repeatedly.
**Trigger seam:** Workflow 1 does not exist in Phase 1. The trigger writes a `trigger_event` row and calls a registered callback (default: log + optional notification). Phases 4+ register the real Workflow-1 launcher. **Do not build Workflow 1.**
**Scheduler:** launchd plist runs `python -m catalyst_trader.calendar.refresh` daily. Daily resolution is sufficient — the trigger window is 1–2 days and holds are one week, so a daily sample catches T-2 and T-1.

### Anti-Patterns to Avoid
- **Coercing partial dates to a day** (`2027-04` → `2027-04-01`) — silently fabricates precision the source doesn't have. Classify as `window`; store the raw string + a precision flag.
- **Mapping ticker→trials by loose sponsor text search** — pulls in collaborator/investigator trials. Use the curated exact-name map + lead-sponsor filter.
- **Deleting unverifiable/resolved catalysts** — never delete; set `status`. Backtest (Phase 7) and audit need the full history, including delisted names.
- **An always-on in-process scheduler for a once-daily job** — launchd + one idempotent script is less code and reboot-safe.
- **A separate code path for ad-hoc injection** — it must flow through the *same* verify pipeline, or user-injected dates escape the two-source rule.

## Data Model (SQLite)

Single file `catalyst.db`. Surrogate integer PKs on every entity (so Phase 2 can reference them as graph nodes). Shape below is the planner's starting point, not gospel.

```sql
-- catalyst: the rolling calendar (DATA-01)
CREATE TABLE catalyst (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  company_name TEXT,
  catalyst_type TEXT NOT NULL CHECK (catalyst_type IN
     ('pdufa','adcom','trial_readout','earnings','conference')),
  event_date TEXT NOT NULL,            -- ISO; may be YYYY, YYYY-MM, or YYYY-MM-DD
  event_date_end TEXT,                 -- set when the source gives a range
  date_precision TEXT NOT NULL CHECK (date_precision IN ('day','month','quarter','year')),
  uncertainty_type TEXT NOT NULL CHECK (uncertainty_type IN ('firm','window','soft')),  -- DATA-04
  status TEXT NOT NULL CHECK (status IN
     ('unverified','verified','excluded','resolved')) DEFAULT 'unverified',              -- DATA-03
  source_origin TEXT NOT NULL CHECK (source_origin IN
     ('clinicaltrials_gov','fmp_earnings','curated_pdufa','ad_hoc_user')),               -- DATA-02
  last_verified_at TEXT,               -- DATA-03 freshness stamp
  external_ref TEXT,                   -- e.g. NCTId, for re-fetch/dedup
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- catalyst_source: provenance rows — the two-source rule lives here (DATA-03)
CREATE TABLE catalyst_source (
  id INTEGER PRIMARY KEY,
  catalyst_id INTEGER NOT NULL REFERENCES catalyst(id),
  source_name TEXT NOT NULL,           -- 'ClinicalTrials.gov' | 'Company IR' | 'FDA' | 'FMP' | user
  source_url TEXT,                     -- required for external; user note for ad-hoc
  source_type TEXT NOT NULL CHECK (source_type IN ('primary','secondary')),
  reported_date TEXT NOT NULL,         -- date THIS source claims
  date_type TEXT NOT NULL CHECK (date_type IN ('estimated','actual')) DEFAULT 'estimated', -- DATA-04: source's own ESTIMATED/ACTUAL; verify re-derives uncertainty from this
  agrees INTEGER NOT NULL DEFAULT 1,   -- does it match the catalyst event_date within tolerance
  retrieved_at TEXT NOT NULL
);

-- universe_snapshot: point-in-time membership, append-only (DATA-06)
CREATE TABLE universe_snapshot (
  id INTEGER PRIMARY KEY,
  as_of_date TEXT NOT NULL,
  ticker TEXT NOT NULL,
  included INTEGER NOT NULL,
  delisted INTEGER NOT NULL DEFAULT 0, -- retain delisted names for backtest (Pitfall: survivorship)
  criteria_json TEXT,                  -- {catalyst_density, market_cap, adv_usd, therapeutic_area}
  reason TEXT
);

CREATE TABLE schema_version (version INTEGER NOT NULL);
```

**Verification rule (DATA-03), enforced in `verify.py` + at the write path:**
- A catalyst is `verified` (and thus `tradeable`) **iff** ≥2 `catalyst_source` rows with `agrees=1`, **at least one `source_type='primary'`** (company IR / FDA / ClinicalTrials.gov), **and** `last_verified_at` within the freshness threshold when the event is near.
- "Excluded from trading" (DATA-03) = `status='excluded'` (or simply not `verified`). A single computed `tradeable` predicate (`status='verified'`) is the only gate any downstream phase queries. Never a boolean scattered across callers.
- **No-LLM-date enforcement:** a pydantic validator rejects any `Catalyst` with zero source rows, and the insert path requires the source rows in the same transaction. There is no code path that writes a date without provenance.
- **Uncertainty re-derivation:** `verify.py` reads the most-authoritative (primary-preferred) source row's `date_type` and passes it to `classify(...)` — it never guesses ESTIMATED vs ACTUAL. This is why `date_type` is persisted per source (DATA-04).

## Point-in-Time Universe (DATA-06)

- **Assembly:** start from a curated `seed_universe.csv` (hand-picked life-science/biotech names with known upcoming catalysts — seed by hand from BiopharmaWatch's free calendar / known 2026 PDUFA names). Then score each against criteria: **catalyst density** (count of upcoming `catalyst` rows in the next N months), **market cap** + **liquidity** (avg daily $ volume) from FMP, **therapeutic area** (from CT.gov `query.cond` / curated). Select ~20.
- **Point-in-time:** each rebuild writes a **new `as_of_date` cohort** (append-only). "Universe as of date D" = the latest snapshot with `as_of_date <= D`. Never overwrite — this is what makes Phase 7's backtest survivorship-free.
- **Delisted names:** explicitly retained (`delisted=1`) so historical backtests don't silently drop the failures (survivorship bias = Pitfall 8 from project research).

## Ad-hoc Injection (DATA-02)

CLI: `python -m catalyst_trader.cli inject --ticker XYZ --type pdufa --date 2026-11-30 [--window-end ...] --source-url ...`. Inserts a `catalyst` with `source_origin='ad_hoc_user'` and **one** `catalyst_source` row (the user's). Because it enters the *same* pipeline, it starts `unverified`/`soft` and only becomes tradeable once a second (ideally primary) source corroborates it during the next `refresh` — the user cannot bypass the two-source rule. This is a feature: user injection is a *lead*, not a green light.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDUFA/AdCom scraping | A live scraper of BiopharmaWatch/RTTNews as the *primary* feed | Hand-curated `pdufa_curated.csv` + two-source verify | Fragile, ToS-gray, no SLA; a broken scraper = a missed/total-loss catalyst |
| HTTP retries/backoff | Custom retry loop | httpx `transport=HTTPTransport(retries=...)` + a tiny backoff wrapper | httpx has transport-level retries built in |
| Partial-date parsing | Regex guessing / dateutil fuzzy | Explicit length check on the raw string (`10`/`7`/`4`) → precision enum | `dateutil` *fabricates* missing components (fills day=today) — the exact bug we must avoid |
| Time-travel in tests | Injecting a fake clock everywhere | freezegun | One decorator; battle-tested |
| Mocking APIs in tests | Custom httpx monkeypatch | pytest-httpx recorded fixtures | Deterministic, offline, native to httpx |
| Scheduling | An in-process daemon | launchd plist | Reboot-safe, no process to babysit, matches fleet convention |
| Schema migrations | Alembic | Numbered `.sql` files + `schema_version` row | ~20 lines at this scale; carries to Phase 2 unchanged |

**Key insight:** In this domain the expensive edge cases are all in *date semantics* (partial dates, estimated-vs-actual, timezone-naive US calendar dates, dates that move) — spend the effort there, and use stdlib/off-the-shelf for everything mechanical.

## Common Pitfalls

### Pitfall 1: Coercing a partial date to a false-precision day (TOTAL-LOSS VECTOR)
**What goes wrong:** `dateutil.parser.parse("2027-04")` returns `2027-04-<today's day>`. A month-only trial estimate becomes a fake exact date; a trade could be timed to a day the source never asserted.
**Why it happens:** ~35% of live CT.gov `primaryCompletionDate` values are partial; naive parsers fill the gaps.
**How to avoid:** Length-check the raw string, store precision explicitly, classify month/year-only as `window`. Exhaustive `test_dates.py`.
**Warning signs:** Any `firm` catalyst whose source is a month-only CT.gov date.

### Pitfall 2: Ticker→trial mapping via loose sponsor search
**What goes wrong:** Collaborator/investigator-sponsored trials get attributed to the wrong company (Vertex query returned Virginia Commonwealth University as lead sponsor). A catalyst is assigned to a name that has no economic exposure to it.
**How to avoid:** Curated `ticker → exact legal leadSponsor name` map; filter to lead-sponsor matches; treat collaborator matches as flagged/optional.
**Warning signs:** `leadSponsor.name` that is a university/hospital/individual under a company ticker.

### Pitfall 3: Ad-hoc dates escaping verification
**What goes wrong:** A convenience "just add this date" path bypasses the two-source rule; a user-typed (or worse, LLM-suggested-to-user) date becomes tradeable.
**How to avoid:** One ingestion→verify pipeline; ad-hoc entries start `unverified` and need corroboration like everything else.

### Pitfall 4: Stale verification near the event
**What goes wrong:** A date verified weeks ago has since moved (PDUFA dates slip, readouts re-guide); the system trades a dead date.
**How to avoid:** `last_verified_at` + the daily `refresh` re-verifies within 48h of the event and excludes anything it can't re-confirm. freezegun tests on the boundary.

### Pitfall 5: Survivorship bias baked into the universe
**What goes wrong:** Rebuilding the universe in place and dropping delisted names makes every future backtest look artificially good.
**How to avoid:** Append-only snapshots; retain delisted names with a flag from day one.

## Runtime State Inventory

Not applicable — greenfield phase, no rename/refactor/migration. (No prior stored data, live-service config, OS-registered state, or build artifacts exist.) The one OS-registered artifact this phase *creates* is the launchd plist (`com.zamvar.catalyst-refresh`) — a Wave item, not pre-existing state.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | ✓ | 3.14.6 | — |
| SQLite (stdlib) | Store | ✓ | 3.53.3 (`enable_load_extension` on) | — |
| ClinicalTrials.gov v2 | DATA-01 trial readouts | ✓ (live-verified) | api 2.0.5 | none needed (free, no auth) |
| FMP API | DATA-01 earnings + DATA-06 fundamentals | ⚠ needs key | free tier 250/day | Manual earnings dates in curated table if key absent |
| launchd | DATA-03 daily refresh, DATA-05 trigger | ✓ (macOS native) | — | cron; or manual run during dev |
| PDUFA/AdCom API | DATA-01 PDUFA | ✗ (none exists) | — | **hand-curated table (the plan)** |

**Missing dependencies with no fallback:** None blocking.
**Missing with fallback:** FMP API key — must be provisioned (`FMP_API_KEY` env var) before earnings/fundamentals work; universe criteria degrade gracefully to curated seed if absent. PDUFA has no API by design → curated table.

## Validation Architecture

*(nyquist_validation = true in config → included.)*

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 |
| Config file | none yet — `[tool.pytest.ini_options]` in `pyproject.toml` (Wave 0) |
| Quick run command | `pytest -x -q` |
| Full suite command | `pytest --cov=catalyst_trader --cov-report=term-missing` |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Automated Command | File |
|-----|----------|-----------|-------------------|------|
| DATA-01 | CT.gov + FMP + curated merge into calendar | integration | `pytest tests/test_clinicaltrials.py tests/test_fmp.py -x` | ❌ Wave 0 |
| DATA-01 | CT.gov date-range query parses nested fields | unit (fixture) | `pytest tests/test_clinicaltrials.py -x` | ❌ Wave 0 |
| DATA-02 | Ad-hoc injection enters same verify pipeline | unit | `pytest tests/test_verify.py::test_adhoc_needs_second_source -x` | ❌ Wave 0 |
| DATA-03 | Two-source rule gates `verified`; single-source stays excluded | unit | `pytest tests/test_verify.py -x` | ❌ Wave 0 |
| DATA-03 | 48h re-verify; stale near-event → excluded | unit (freezegun) | `pytest tests/test_triggers.py::test_48h_reverify -x` | ❌ Wave 0 |
| DATA-04 | Partial date → window; corroborated day → firm | unit | `pytest tests/test_dates.py -x` | ❌ Wave 0 |
| DATA-05 | Verified catalyst 1–2d out fires trigger seam | unit (freezegun) | `pytest tests/test_triggers.py::test_t2_trigger -x` | ❌ Wave 0 |
| DATA-06 | Point-in-time snapshot; delisted retained; as-of query | unit | `pytest tests/test_universe.py -x` | ❌ Wave 0 |
| (invariant) | No catalyst persists without a source row | unit | `pytest tests/test_verify.py::test_no_date_without_source -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest -x -q`
- **Per wave merge:** `pytest --cov=catalyst_trader --cov-report=term-missing`
- **Phase gate:** full suite green + coverage on the date/verify path before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `pyproject.toml` with `[tool.pytest.ini_options]` + dev deps + ruff config — no test infra exists yet
- [ ] `tests/conftest.py` — tmp/in-memory DB fixture + frozen-clock fixture
- [ ] `tests/fixtures/` — record live CT.gov JSON (partial-date + full-date + collaborator cases) and FMP earnings-calendar + confirmed JSON (needs `FMP_API_KEY`)
- [ ] Framework install: `pip install pytest pytest-httpx freezegun pytest-cov`
- [ ] `tests/test_dates.py` — the money-critical partial-date/precision suite (write FIRST, TDD)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ClinicalTrials.gov API **v1** (`/api/query/...`) | **v2** (`/api/v2/studies`, OpenAPI 3.0, nested `protocolSection`) | v1 retired ~2024 | Use v2 field paths above; v1 tutorials online are wrong |
| FMP `/api/v3/...` legacy endpoints | FMP `**/stable/**` endpoints | 2025→ | Use `/stable/earnings-calendar`; v3 examples are legacy |
| `robin_stocks` / unofficial for any RH data | Official RH Agentic MCP (Phase 11 only) | 2026-05 | Not this phase — noted so no data pull sneaks in via RH |

**Deprecated/outdated:** CT.gov v1 API (retired); FMP v3 endpoints (legacy — still up but not `stable`); `dateutil` fuzzy parsing for these dates (fabricates precision).

## Open Questions

1. **Exact FMP earnings-calendar + confirmed field names.**
   - Known: endpoint paths, 250/day free tier, that a confirmed endpoint exists separately.
   - Unclear: precise JSON keys (FMP docs 403 to automated fetch).
   - Recommendation: capture live fixtures with the real key in Wave 0 before writing the parser; treat as MEDIUM until then.
2. **Freshness threshold for `last_verified_at`.**
   - Requirement says re-verify within 48h of the event. Open: how stale is too stale *far* from the event (e.g. 7 days)?
   - Recommendation: make it a config tunable (`config.py`); default 48h near-event, 7d otherwise.
3. **CT.gov hard rate limit.**
   - ~50/min is secondary-sourced (MEDIUM), no headers exposed.
   - Recommendation: 1.5s spacing + backoff; irrelevant at 20 names/day but keep the wrapper.
4. **Seed universe origin.**
   - Recommendation: hand-seed ~20-30 names from BiopharmaWatch's free 2026 PDUFA calendar + known catalyst names, then filter by criteria. A human curation task, not code.

## Sources

### Primary (HIGH confidence)
- **ClinicalTrials.gov API v2 — live calls during this research** (`/api/v2/studies`, `/api/v2/version` → 2.0.5): verified query params (`query.spons`, `filter.overallStatus`, `filter.advanced=AREA[...]RANGE[...]`, `fields`, `pageSize`, `nextPageToken`, `countTotal`), nested response field paths, partial-date behavior (`2027-04`, `2032-12`), ESTIMATED/ACTUAL typing, sponsor-mapping fuzziness.
- PyPI version checks (2026-08-14): httpx 0.28.1, pydantic 2.13.4, pytest 9.1.1, pytest-httpx 0.36.2, freezegun 1.5.5, sqlite-vec 0.1.9, claude-agent-sdk 0.2.138.
- Local env probe: Python 3.14.6, SQLite 3.53.3, `enable_load_extension` available.
- Project docs: CLAUDE.md (stack decisions), `.planning/research/STACK.md` + `SUMMARY.md` (catalyst-data note, pitfalls), REQUIREMENTS.md, PROJECT.md.

### Secondary (MEDIUM confidence)
- FMP earnings calendar endpoint + 250/day free tier + confirmed-vs-estimated split — FMP docs/search ([earnings-calendar](https://site.financialmodelingprep.com/developer/docs/stable/earnings-calendar), [pricing/FAQ](https://site.financialmodelingprep.com/faqs)). Exact field names to confirm live.
- PDUFA/AdCom no-free-API — cross-verified across [RTTNews](https://www.rttnews.com/products/biotechfdacalendar.aspx), [BPIQ](https://app.bpiq.com/pdufa-calendar), [BiopharmaWatch](https://www.biopharmawatch.com/fda-calendar), [TheraRadar](https://theraradar.com/dashboards/pdufa-calendar/), [FDATracker](https://www.fdatracker.com/fda-calendar/), [Dan Sfera](https://dansfera.com/).
- CT.gov ~50 req/min rate guidance — community/secondary (no official headers).

### Tertiary (LOW confidence)
- None load-bearing. (Exact FMP field names deferred to build-time fixture capture.)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI + local interpreter today.
- ClinicalTrials.gov v2: HIGH — live-verified end-to-end including the partial-date and sponsor-mapping gotchas.
- FMP: MEDIUM — endpoint/tier confirmed; exact fields pending live fixture (Wave 0).
- PDUFA landscape: HIGH — negative claim cross-verified across 6 trackers.
- Data model / verification design: MEDIUM-HIGH — derived directly from the requirements + verified source-data shapes.
- Pitfalls: HIGH — the two load-bearing ones (partial dates, sponsor fuzziness) were reproduced live.

**Research date:** 2026-08-14
**Valid until:** ~2026-09-14 (30 days; CT.gov v2 and FMP are stable APIs. Re-verify FMP field names at build; re-check package pins.)
