# Test Fixtures

Recorded API responses used by the provider parsers (offline, deterministic — CI never hits live APIs).

## ClinicalTrials.gov v2 (LIVE-CAPTURED)

- **Origin URL:** `GET https://clinicaltrials.gov/api/v2/studies?query.spons=Vertex%20Pharmaceuticals%20Incorporated&pageSize=200&countTotal=true`
- **Captured:** 2026-08-14 (API v2, free, no auth)
- **Trimmed to** `protocolSection.{identificationModule, statusModule, sponsorCollaboratorsModule, designModule}` — the exact nested field paths the parser reads are preserved verbatim (`primaryCompletionDateStruct.{date,type}`, `identificationModule.nctId`, `sponsorCollaboratorsModule.leadSponsor.name`, `designModule.phases`).

| Fixture | NCTId | primaryCompletionDate | leadSponsor | Why kept |
|---------|-------|-----------------------|-------------|----------|
| `ctgov_partial_date.json` | NCT00923728 | `2010-03` (ESTIMATED) | Vertex Pharmaceuticals Incorporated | **Month-only date** — the partial-date total-loss vector. Parser must classify → `window`, never coerce to a day. |
| `ctgov_full_date.json` | NCT06226454 | `2024-06-12` (ACTUAL) | Vertex Pharmaceuticals Incorporated | Full `YYYY-MM-DD` date, `type=ACTUAL`. |
| `ctgov_collaborator.json` | NCT07700225 | `2032-12` (ESTIMATED) | Virginia Commonwealth University | **Sponsor-fuzziness gotcha** — a `query.spons=Vertex` hit whose lead sponsor is a university (Vertex is only a collaborator). Do NOT attribute to VRTX by loose sponsor text alone. |

## FMP Earnings (DOCUMENTED-SHAPE — NOT LIVE)

- **Status:** `FMP_API_KEY` was **absent** at capture time (2026-08-14), so these are hand-built to the *documented/expected* shape, not a live pull.
- **⚠️ Re-confirm before trusting the FMP parser (Plan 03).** Per RESEARCH Open Question #1, the exact JSON field names MUST be re-verified against a live response before the parser is trusted. FMP docs return HTTP 403 to automated fetch, so a real key + a live capture is the only way to lock the field names.
- `fmp_earnings_calendar.json` — expected shape of `GET /stable/earnings-calendar?from=&to=&apikey=`: `{date, symbol, epsEstimated, eps, revenueEstimated, revenue}` (`eps`/`revenue` null until reported).
- `fmp_earnings_confirmed.json` — expected shape of the separate "earnings confirmed" endpoint (company-confirmed announcements — used to promote a catalyst to `firm`).

### To re-capture FMP fixtures live (when a key is provisioned)

```bash
export FMP_API_KEY=...   # never commit
curl "https://financialmodelingprep.com/stable/earnings-calendar?from=$(date +%F)&to=$(date -v+30d +%F)&apikey=$FMP_API_KEY" > tests/fixtures/fmp_earnings_calendar.json
# then update this README: change "DOCUMENTED-SHAPE" -> "LIVE-CAPTURED", set the capture date.
```
