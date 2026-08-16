"""Our own PDUFA/AdCom source from SEC 8-K filings (providers/pdufa_edgar.py) — offline.

The provider discovers PDUFA 8-Ks via EDGAR full-text search (CIK-filtered to the universe),
fetches the matched EX-99.1 exhibit (RAW HTML, as the live .htm delivers), normalizes HTML->text
(tag-strip) FIRST, then deterministically regex-extracts the date verbatim-adjacent to a
PDUFA/target-action/goal/AdCom keyword (no-LLM-dates, cite-or-drop), and emits a Catalyst with a
SINGLE source_name="SEC EDGAR" primary source that self-verifies via the DATA-03 amendment.

The offline-green/live-broken trap is closed here: fixtures are REAL-HTML-shaped 8-K exhibits with
tags interspersed AROUND and BETWEEN the keyword and the date, and _extract tag-strips before the
regex. ZERO live API — efts JSON + 8-K exhibit HTML are mocked; edgar.Company is faked.
"""

import re

from catalyst_trader.models import CatalystType


# ── Task 1: HTML->text normalize + deterministic extraction ─────────────────────────────────


def test_normalize_rejoins_tag_split_keyword_date():
    """A tag-split keyword/date (`date</span> of <span>April 28, 2027`) must NOT match the regex
    on RAW HTML but MUST match after _normalize — proving tag-strip precedes the regex (the fix
    that closes the offline-green/live-broken trap)."""
    from catalyst_trader.providers import pdufa_edgar

    raw = "PDUFA target action date</span> of <span>April 28, 2027"
    assert pdufa_edgar._PDUFA_RX.search(raw) is None  # raw HTML breaks ~40-char adjacency
    text = pdufa_edgar._normalize(raw)
    m = pdufa_edgar._PDUFA_RX.search(text)  # adjacency restored after tag-strip
    assert m is not None
    assert m.group(1) == "April 28, 2027"


def _load_htm(name):
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / name).read_text()


def test_extract_imnm_high():
    from catalyst_trader.providers import pdufa_edgar

    out = pdufa_edgar._extract(_load_htm("edgar_8k_imnm.htm"), "2026-08-11")
    pdufa = [c for c in out if c["catalyst_type"] == CatalystType.pdufa]
    assert len(pdufa) == 1  # date repeated 3x -> deduped to one candidate
    assert pdufa[0]["event_date"] == "2027-04-28"
    assert pdufa[0]["confidence"] == "HIGH"


def test_extract_capr_high():
    from catalyst_trader.providers import pdufa_edgar

    out = pdufa_edgar._extract(_load_htm("edgar_8k_capr.htm"), "2026-05-12")
    pdufa = [c for c in out if c["catalyst_type"] == CatalystType.pdufa]
    assert len(pdufa) == 1
    assert pdufa[0]["event_date"] == "2026-08-22"
    assert pdufa[0]["confidence"] == "HIGH"


def test_extract_no_keyword_no_date():
    """no-LLM-dates: a bare date with NO PDUFA/target-action/goal/AdCom keyword nearby is
    NEVER emitted."""
    from catalyst_trader.providers import pdufa_edgar

    html = "<html><body><p>The board met on April 28, 2027 to discuss strategy.</p></body></html>"
    assert pdufa_edgar._extract(html, "2026-08-11") == []


def test_extract_unparseable_date_dropped():
    """cite-or-drop: a keyword followed by a garbage date does not normalize -> dropped."""
    from catalyst_trader.providers import pdufa_edgar

    html = "<p>PDUFA target action date of Someday 99, 20XX for the drug.</p>"
    assert pdufa_edgar._extract(html, "2026-08-11") == []


def test_extract_multiple_dates_medium():
    """Two DIFFERENT candidate dates near keywords -> MEDIUM (routes to review, never auto-HIGH)."""
    from catalyst_trader.providers import pdufa_edgar

    html = (
        "<p>PDUFA target action date of April 28, 2027 in the release,</p>"
        "<p>but a PDUFA target action date of June 15, 2027 appears elsewhere.</p>"
    )
    out = pdufa_edgar._extract(html, "2026-08-11")
    dates = {c["event_date"] for c in out}
    assert dates == {"2027-04-28", "2027-06-15"}
    assert all(c["confidence"] == "MEDIUM" for c in out)


def test_extract_target_action_without_pdufa_medium():
    """'target action date of <date>' with NO 'PDUFA' token -> MEDIUM (human confirm)."""
    from catalyst_trader.providers import pdufa_edgar

    html = "<p>The FDA set a target action date of August 22, 2026 for the application.</p>"
    out = pdufa_edgar._extract(html, "2026-05-12")
    assert len(out) == 1
    assert out[0]["event_date"] == "2026-08-22"
    assert out[0]["confidence"] == "MEDIUM"


def test_extract_adcom():
    """An AdCom 'advisory committee meeting ... on <date>' -> catalyst_type adcom."""
    from catalyst_trader.providers import pdufa_edgar

    html = (
        "<p>The FDA has scheduled an advisory committee meeting to review the BLA "
        "on <span>September 10, 2026</span>.</p>"
    )
    out = pdufa_edgar._extract(html, "2026-05-12")
    adcom = [c for c in out if c["catalyst_type"] == CatalystType.adcom]
    assert len(adcom) == 1
    assert adcom[0]["event_date"] == "2026-09-10"


def test_no_network_in_extract():
    """No LLM/network call anywhere in _extract/_normalize — pure regex over tag-stripped text."""
    import inspect

    from catalyst_trader.providers import pdufa_edgar

    src = inspect.getsource(pdufa_edgar._extract) + inspect.getsource(pdufa_edgar._normalize)
    assert not re.search(r"get_json|get_text|httpx|requests|anthropic|openai", src)
