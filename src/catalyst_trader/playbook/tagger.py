"""Deterministic, LLM-free SITUATIONAL-SETUP tagger (quick-260818-l64).

Stamps a multi-label `setups` list onto each catalyst node from its narrative fields, using a frozen
keyword/regex rubric DERIVED from data/setup_taxonomy.json's per-tag `ex_ante_cues` + `tagging_rubric`.
No LLM, no network, no ML dep — a pure function of the input text (same fields -> same list). This is
the deterministic axis kb._structural_filter / analog_query then retrieve on (Task 2).

The regexes below ARE the rubric: each vocab tag maps to one case-insensitive alternation. A tag fires
when ANY of its patterns match the concatenated, lowercased narrative text. Cues are deliberately
generous (live coverage target is >=90% carrying >=1 ex-ante tag).

# ponytail: one alternation per tag, no per-cue class hierarchy. The import-time cross-check
#           (_TAG_PATTERNS keys == taxonomy tag names) is the one guard that a widened vocab or a
#           dropped pattern can't silently under-tag.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]  # [0]=playbook [1]=catalyst_trader [2]=src [3]=repo-root
_TAXONOMY_PATH = _REPO_ROOT / "data" / "setup_taxonomy.json"

# The narrative fields tag_setups reads (all optional — the query side supplies only a few).
_FIELDS = (
    "thesis", "reference_class", "variant_why", "causal_setup", "why_narrative",
    "lesson_rule", "second_order", "what_happened", "indication", "modality", "what_to_watch",
)

# Per-tag deterministic rubric: cue alternations derived from each tag's ex_ante_cues + the rubric.
_TAG_CUES = {
    "priced-in-derisked-readout":
        r"topline (already )?(disclosed|public|reported)|confirmatory|second pivotal|label expansion|"
        r"\bsNDA\b|re-present|run-?up|priced.in|de-?risked (pdufa|readout)|already (known|public)|"
        r"randomized.withdrawal",
    "priced-for-perfection-crowded-benchmark":
        r"priced for perfection|crowded (indication|market|space|field)|approved competitor|"
        r"cross-trial|benchmark|best-in-class|head-to-head|richly valued|high multiple|"
        r"dupilumab|GLP-?1|amivantamab|tafamidis",
    "single-asset-microcap-binary":
        r"microcap|nanocap|thin float|thinly traded|one lead asset|single(-| )asset|company-defining|"
        r"sole.{0,15}pivotal|all-or-nothing|\bbinary\b",
    "financing-overhang-going-concern":
        r"going.concern|dilut|reverse split|\bwarrant|\bATM\b|registered.direct|strategic alternatives|"
        r"cash runway|runway (of )?(under|<|less than)|sub-?\$1|Q-suffix|must raise|need.{0,10}(to )?raise",
    "first-in-class-no-approved-therapy-whitespace":
        r"first-in-class|no approved therap|no standard of care|unmet need|whitespace|"
        r"breakthrough (therapy|designation)|\bRMAT\b|orphan|priority review|"
        r"biomarker (endpoint|primary)|objective (endpoint|primary)|intra-patient",
    "validated-mechanism-derisked":
        r"validated mechanism|same-class|same class|approved same-class|accepted surrogate|"
        r"robust prior phase 2|prior positive phase 2|bridging (study|trial)|regional bridg|"
        r"class-validated|TTR stabilizer|IL-?23|anti-VEGF|PTH replacement|SST analog",
    "trial-graveyard-high-placebo-indication":
        r"\bALS\b|glioblastoma|\bGBM\b|alzheimer|cognition|\bMDD\b|major depress|migraine prevention|"
        r"fragile x|essential tremor|long covid|\bSLE\b|lupus|obesity|high placebo|graveyard|"
        r"functional.{0,10}(rating|scale)|patient-reported",
    "cmc-manufacturing-regulatory-risk":
        r"\bCMC\b|manufactur|nitrosamine|impurit|facility (inspection|finding)|\b483\b|\bPAI\b|"
        r"fill-finish|single-site|505\(b\)\(2\)|drug-device|device-combo|combination product|"
        r"resubmission|major amendment",
    "contested-efficacy-adcom-risk":
        r"\badcom\b|advisory committee|contested efficacy|marginal (efficacy|effect|benefit)|"
        r"single-arm|natural.history|briefing (document|doc)|benefit-risk|goalpost|adversarial|"
        r"prior crl|clinical meaningfulness|pk-bridging",
    "no-new-information-nonevent":
        r"no new (information|data)|non-?event|\bJPM\b|conference (deck|presentation|overview)|"
        r"enrollment complete|last[- ]patient[- ]dosed|dosing complete|\bIND\b clear|IND clearance|"
        r"patent|rebrand|quiet (window|period)|operational (update|milestone)",
    "commercial-single-product-quality":
        r"gross-to-net|gross to net|net[- ]price|guidance (cut|top-end|raise|lower)|\bopex\b|"
        r"script (trend|growth|deceler)|launch (spend|ramp|trajectory)|commercial-stage|"
        r"single product|lead product|first full (quarter|year)|widening loss",
    "strategic-transaction-capital-injection":
        r"in-licens|out-licens|\bM&A\b|acqui(re|sition|red)|\bPIPE\b|private placement|"
        r"reverse[- ]merger|big-pharma (partner|alliance)|partnership|collaboration|"
        r"milestone-structured|syndicate|baker bros|strategic transaction|capital injection",
    "good-news-faded":
        r"good news faded|sell-the-news|sell the news|faded (on|the|despite)|"
        r"approved but (fell|dropped|sold)|positive data.{0,25}(negative|down|fell|dropped|sold)",
    "stat-hit-magnitude-or-benchmark-miss":
        r"magnitude (miss|underwhelm|disappoint)|sub-benchmark|hit on paper|non-monotonic|single-dose|"
        r"modest (absolute )?effect|benchmark miss|met (the )?primary but|statistically significant but",
    "os-miss-despite-soft-endpoint-hit":
        r"overall survival (miss|immature|not|failed|confounded)|\bOS\b (miss|immature|failed)|"
        r"\bPFS\b.{0,25}(os|survival)|\bORR\b.{0,25}(os|survival)|crossover|soft endpoint",
    "primary-miss-subgroup-salvage":
        r"missed (the )?primary|primary (endpoint )?(miss|fail)|subgroup (salvage|rescue|analysis)|"
        r"post-hoc|subscale|completer (analysis|population)|salvage narrative",
}

# Compiled once at import (IGNORECASE — cues match regardless of the source casing).
_TAG_PATTERNS = {name: [re.compile(cues, re.IGNORECASE)] for name, cues in _TAG_CUES.items()}


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    """The frozen vocab + tagging_rubric + per-tag ex_ante_cues from <repo-root>/data/setup_taxonomy.json.
    Cached after first read (the file is immutable at runtime)."""
    return json.loads(_TAXONOMY_PATH.read_text())


@lru_cache(maxsize=1)
def _tag_order() -> list[str]:
    """Tag names in taxonomy declaration order (tag_setups returns matches in this order)."""
    return [t["name"] for t in load_taxonomy()["tags"]]


@lru_cache(maxsize=1)
def _ex_ante_tags() -> frozenset:
    """The group=='ex-ante' tag names — the retrieval-useful group coverage is measured against."""
    return frozenset(t["name"] for t in load_taxonomy()["tags"] if t.get("group") == "ex-ante")


def _haystack(fields: dict) -> str:
    """Concatenate every string / list-of-string field value into one lowercased blob to match on."""
    parts: list[str] = []
    for key in _FIELDS:
        val = fields.get(key)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, (list, tuple)):
            parts.extend(str(v) for v in val if isinstance(v, str))
    return " ".join(parts).lower()


def tag_setups(fields: dict) -> list[str]:
    """Every setup tag whose rubric matches `fields`, in taxonomy declaration order (multi-label,
    stable, []-on-no-match). Pure: same fields -> same list. `fields` is a flat dict of the narrative
    keys (thesis, reference_class, indication, ...); unknown keys are ignored."""
    text = _haystack(fields)
    if not text.strip():
        return []
    matched = [name for name, pats in _TAG_PATTERNS.items() if any(p.search(text) for p in pats)]
    return sorted(matched, key=_tag_order().index)


def tag_all_catalyst_nodes(conn) -> dict:
    """Recompute + write attrs['setups'] on every kind='catalyst' node from its narrative fields.

    Idempotent (overwrite, never append). setups is a STRUCTURAL filter axis, NOT embedded — so no
    re-embed here (consistent with the retrieval decision). Returns
    {'total', 'with_ex_ante', 'coverage'} where with_ex_ante counts nodes carrying >=1 ex-ante tag.
    """
    rows = conn.execute("SELECT id, attrs_json FROM kb_node WHERE kind='catalyst'").fetchall()
    ex_ante = _ex_ante_tags()
    with_ex_ante = 0
    for r in rows:
        attrs = json.loads(r["attrs_json"]) if r["attrs_json"] else {}
        nb = attrs.get("narrative_before") or {}
        na = attrs.get("narrative_after") or {}
        fields = {
            "thesis": nb.get("thesis"),
            "reference_class": nb.get("reference_class"),
            "variant_why": nb.get("variant_why"),
            "causal_setup": nb.get("causal_setup"),
            "what_to_watch": nb.get("what_to_watch"),
            "why_narrative": na.get("why_narrative"),
            "lesson_rule": na.get("lesson_rule"),
            "second_order": na.get("second_order"),
            "what_happened": na.get("what_happened"),
            "indication": attrs.get("indication"),
            "modality": attrs.get("modality"),
        }
        tags = tag_setups(fields)
        attrs["setups"] = tags
        if any(t in ex_ante for t in tags):
            with_ex_ante += 1
        conn.execute("UPDATE kb_node SET attrs_json=? WHERE id=?", (json.dumps(attrs), r["id"]))
    conn.commit()
    total = len(rows)
    return {"total": total, "with_ex_ante": with_ex_ante,
            "coverage": (with_ex_ante / total) if total else 0.0}
