"""Plan 06.10-06 Task 1 — the single provider registry (build_providers) + cadence table.

Zero live API. build_providers only WIRES the provider callables (it never invokes them), so a
fake settings object exercises the full wiring offline. The lifted per-ticker closures must keep
their @functools.cache (no behaviour change from the shakedown's _live_providers)."""

import inspect
from types import SimpleNamespace

from catalyst_trader.providers import edgar, finra, registry
from scripts import shakedown as sd

_SLOTS = ("prices", "options", "finra", "edgar", "financials", "macro",
          "clinicaltrials", "earnings", "pdufa")


def _settings(**over):
    base = dict(fred_api_key="k", sec_user_agent="ua@x.com", fmp_api_key="fk",
                alpha_vantage_api_key=None, tiingo_api_key=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_build_providers_has_all_slots():
    p = registry.build_providers(_settings(), end="2026-01-30")
    for slot in _SLOTS:
        assert slot in p, f"missing provider slot: {slot}"
    # every wired slot (macro may degrade to None without a key) is callable when present
    for slot in _SLOTS:
        if p[slot] is not None:
            assert callable(p[slot]), f"{slot} not callable"


def test_financials_slot_uses_edgar_fundamentals(monkeypatch):
    seen = []
    monkeypatch.setattr(edgar, "fundamentals", lambda tk: seen.append(tk) or {"x": 1})
    p = registry.build_providers(_settings(), end="2026-01-30")
    assert p["financials"]("ABCD") == {"x": 1}
    assert seen == ["ABCD"]


def test_earnings_slot_uses_fallback(monkeypatch):
    # FMP degrades (raises) -> the fallback combinator drops to the Nasdaq fn (no fabrication)
    from catalyst_trader.providers import fmp, nasdaq_earnings
    monkeypatch.setattr(fmp, "fetch_earnings",
                        lambda tks, s, e: (_ for _ in ()).throw(RuntimeError("no key")))
    monkeypatch.setattr(nasdaq_earnings, "fetch", lambda tks, s, e: ["NASDAQ_EVENT"])
    p = registry.build_providers(_settings(), end="2026-01-30")
    assert p["earnings"](["ABCD"], "2026-01-01", "2026-02-01") == ["NASDAQ_EVENT"]


def test_macro_slot_degrades_without_fred_key():
    p = registry.build_providers(_settings(fred_api_key=None), end="2026-01-30")
    assert p["macro"] is None  # no key -> the macro slot degrades, never crashes


def test_closures_keep_cache(monkeypatch):
    """A lifted per-ticker closure called twice with the same ticker hits the underlying provider
    ONCE — the @functools.cache is preserved, so a degrading source is not re-hit 52x/ticker."""
    calls = {"edgar": 0, "finra": 0}
    monkeypatch.setattr(edgar, "fetch", lambda tk: calls.__setitem__("edgar", calls["edgar"] + 1))
    monkeypatch.setattr(finra, "fetch", lambda tk, sd: calls.__setitem__("finra", calls["finra"] + 1))
    p = registry.build_providers(_settings(), end="2026-01-30")
    p["edgar"]("ABCD"); p["edgar"]("ABCD"); p["edgar"]("ABCD")
    p["finra"]("WXYZ"); p["finra"]("WXYZ")
    assert calls["edgar"] == 1, "edgar closure lost its @functools.cache"
    assert calls["finra"] == 1, "finra closure lost its @functools.cache"


def test_cadence_table_covers_every_source():
    p = registry.build_providers(_settings(), end="2026-01-30")
    for slot in p:
        assert slot in registry.CADENCE, f"CADENCE missing an entry for {slot}"
        assert isinstance(registry.CADENCE[slot], int) and registry.CADENCE[slot] > 0


def test_shakedown_uses_registry():
    """shakedown is refactored onto the shared registry — the duplicated provider dict is gone."""
    assert "build_providers" in inspect.getsource(sd), "shakedown does not import the shared registry"
    live = sd._live_providers("2026-01-30")
    for slot in ("prices", "options", "finra", "edgar", "clinicaltrials", "earnings", "pdufa"):
        assert slot in live
