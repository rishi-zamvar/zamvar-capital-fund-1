"""evidence_ref mint + resolve (CALL-04's deterministic half). Analysts cite KB
facts as `kb:<node_id>` and quant-derived claims as `tool:<name>#<inputs_hash>`;
the verifier resolves those refs structurally (no LLM) and gates on a quote
substring check. Semantic support-checking lives in the verifier (Plan 06)."""

from catalyst_trader.desk import evidence
from catalyst_trader.kb import EvidenceSource, KBNode, insert_claim
from catalyst_trader.quant.result import ToolResult


def _seed_evidence(conn, url="https://ct.gov/NCT1", quote="Primary endpoint MET at p<0.001"):
    ev = EvidenceSource(url=url, retrieved_at="2026-08-14", snippet_hash="h1", quote=quote)
    insert_claim(conn, KBNode(kind="playbook", attrs={"x": 1}), [ev])
    row = conn.execute("SELECT id FROM kb_node WHERE kind='evidence_source'").fetchone()
    return row["id"]


def test_kb_ref_mints_expected_string():
    assert evidence.kb_ref(7) == "kb:7"


def test_tool_ref_is_stable_for_same_inputs():
    r1 = ToolResult(tool="base_rate", tool_version="1", inputs={"phase": "3", "metric": "approval"})
    # same inputs, different key order -> same hash (sorted keys)
    r2 = ToolResult(tool="base_rate", tool_version="1", inputs={"metric": "approval", "phase": "3"})
    ref1, ref2 = evidence.tool_ref(r1), evidence.tool_ref(r2)
    assert ref1 == ref2
    assert ref1.startswith("tool:base_rate#")


def test_tool_ref_differs_for_different_inputs():
    r1 = ToolResult(tool="base_rate", tool_version="1", inputs={"phase": "3"})
    r2 = ToolResult(tool="base_rate", tool_version="1", inputs={"phase": "2"})
    assert evidence.tool_ref(r1) != evidence.tool_ref(r2)


def test_resolve_kb_ref_returns_source_attrs(db):
    nid = _seed_evidence(db)
    attrs = evidence.resolve(db, f"kb:{nid}")
    assert attrs is not None
    assert attrs["url"] == "https://ct.gov/NCT1"
    assert attrs["quote"] == "Primary endpoint MET at p<0.001"


def test_resolve_kb_ref_missing_node_returns_none(db):
    assert evidence.resolve(db, "kb:99999") is None


def test_resolve_kb_ref_non_evidence_node_returns_none(db):
    # a claim (playbook) node id is not an evidence_source -> unresolvable
    nid = insert_claim(
        db,
        KBNode(kind="playbook", attrs={"x": 1}),
        [EvidenceSource(url="u", retrieved_at="t", snippet_hash="h")],
    )
    assert evidence.resolve(db, f"kb:{nid}") is None


def test_resolve_tool_ref_is_resolved_by_construction(db):
    r = ToolResult(tool="rnpv", tool_version="1", inputs={"pos": 0.6})
    ref = evidence.tool_ref(r)
    marker = evidence.resolve(db, ref)
    assert marker is not None
    assert marker["kind"] == "tool"
    assert marker["tool"] == "rnpv"


def test_resolve_garbage_returns_none(db):
    assert evidence.resolve(db, "garbage") is None
    assert evidence.resolve(db, "kb:notanint") is None


def test_quote_supported_substring_case_and_whitespace_insensitive():
    src = {"quote": "The Primary Endpoint was   MET at p<0.001 in the pivotal trial."}
    assert evidence.quote_supported(src, "primary endpoint was met") is True
    # extra internal whitespace in the claim still matches
    assert evidence.quote_supported(src, "endpoint   was met") is True


def test_quote_supported_rejects_unsupported_claim():
    src = {"quote": "Primary endpoint met."}
    assert evidence.quote_supported(src, "primary endpoint missed") is False


def test_quote_supported_no_quote_returns_false():
    assert evidence.quote_supported({"quote": None}, "anything") is False
    assert evidence.quote_supported({}, "anything") is False
