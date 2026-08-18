"""The warm-playbook RECORD CONTRACT + narrative-card composer + node-attr mappers.

Two layers per catalyst (research D+E):
- STRUCTURED ENVELOPE — deterministic facts that filter retrieval: ticker, type, indication,
  modality, knowable_asof (the leak gate), event_date, outcome_label, SIGNED move, confidence,
  move_consistency_flag, and the ~18-field driver taxonomy (research A §6).
- NARRATIVE BODY — the reasoning substrate that gets embedded: before {thesis, causal_setup,
  reference_class, variant_why, what_to_watch, what_would_change_our_mind}; after {what_happened,
  why_narrative, surprise_vs_prior, which_disconfirmer_fired, lesson_rule, second_order, process_grade}.

MONEY-PATH invariants (locked, tested):
- to_outcome_attrs emits the outcome key literally "move" as the SIGNED decimal — the exact key
  and sign desk/builder.py:69 `_split_moves` consumes (`a["outcome"]["move"]`, split by sign).
- to_catalyst_attrs puts every structural-filter key at the TOP LEVEL of the attrs dict, because
  kb._structural_filter reads json_extract(attrs_json,'$.<key>') — top-level only (kb.py:150-152).
- compose_card is EXACTLY thesis + causal_setup + reference_class + why_narrative — the embed_text
  handed to kb.insert_claim; nothing else rides in the vector.

Pure module: no kb/db/network/LLM import. The writer (Plan 04) picks kb_node kinds; not our job.
"""

from pydantic import BaseModel, ConfigDict, model_validator

# outcome_label -> expected sign of the realized move. A record whose label implies a direction the
# signed move contradicts is flagged (not rejected — the disagreement is itself a signal to surface).
_POSITIVE_LABELS = frozenset({"approve", "approval", "hit", "beat", "positive", "win"})
_NEGATIVE_LABELS = frozenset({"crl", "reject", "rejection", "miss", "fail", "negative", "loss"})


def compute_move_consistency(label: str | None, signed_move: float | None) -> bool:
    """True when outcome_label implies a direction the signed move contradicts.

    None move -> False (unavailable, not a disagreement). A label outside the known direction sets
    -> False (no directional expectation to contradict).
    """
    if signed_move is None or label is None:
        return False
    key = label.strip().lower()
    if key in _POSITIVE_LABELS:
        return signed_move < 0
    if key in _NEGATIVE_LABELS:
        return signed_move > 0
    return False


class DriverClaim(BaseModel):
    """One taxonomy driver (research A §6) with its citation. All fields required: a driver with no
    quote/source is dropped by the EXTRACTOR (Plan 03), never constructed here (cite-or-drop)."""

    model_config = ConfigDict(extra="forbid")

    factor: str
    value: str
    evidence_quote: str
    source_url: str


class Citation(BaseModel):
    """A record-level source. Downstream kb.insert_claim enforces >=1 CITES edge; the contract
    mirrors that here by requiring a non-empty citations list on CatalystRecord."""

    model_config = ConfigDict(extra="forbid")

    url: str
    quote: str
    snippet_hash: str


class NarrativeBefore(BaseModel):
    """The pre-event reasoning substrate (variant view + disconfirmers)."""

    model_config = ConfigDict(extra="forbid")

    thesis: str
    causal_setup: str
    reference_class: str
    variant_why: str
    what_to_watch: list[str]
    what_would_change_our_mind: list[str]


class NarrativeAfter(BaseModel):
    """The post-event reasoning substrate (what happened + the lesson)."""

    model_config = ConfigDict(extra="forbid")

    what_happened: str
    why_narrative: str
    surprise_vs_prior: str
    which_disconfirmer_fired: str
    lesson_rule: str
    process_grade: str
    second_order: str | None = None


class CatalystRecord(BaseModel):
    """The full warm-playbook case: structured envelope + driver taxonomy + before/after narrative
    + outcome label + SIGNED move + citations. The single typed contract every later task builds on."""

    model_config = ConfigDict(extra="forbid")

    catalyst_id: int
    ticker: str
    catalyst_type: str
    indication: str
    modality: str
    event_date: str
    knowable_asof: str  # the leak gate — a TOP-LEVEL filter key downstream

    outcome_label: str
    signed_move: float | None  # SIGNED; None on a month-precision / no-move row
    move_window: str
    confidence: float
    move_consistency_flag: bool = False  # computed in _set_move_consistency

    drivers: list[DriverClaim]
    narrative_before: NarrativeBefore
    narrative_after: NarrativeAfter
    citations: list[Citation]

    @model_validator(mode="after")
    def _validate(self) -> "CatalystRecord":
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {self.confidence!r}")
        if not self.citations:
            raise ValueError("citations must be non-empty (cite-or-drop)")
        self.move_consistency_flag = compute_move_consistency(self.outcome_label, self.signed_move)
        return self


def compose_card(record: CatalystRecord) -> str:
    """The composed narrative card = thesis + causal_setup + reference_class + why_narrative, and
    NOTHING else. This exact string is the embed_text handed to kb.insert_claim (research C/D/E):
    the query side embeds "<type> catalyst for <target>: <thesis>" (builder.py:62), so the card
    leads with the thesis and stays reasoning-only (no numbers, no watch-list, no variant aside)."""
    b, a = record.narrative_before, record.narrative_after
    return "\n".join(
        [
            f"THESIS: {b.thesis}",
            f"CAUSAL SETUP: {b.causal_setup}",
            f"REFERENCE CLASS: {b.reference_class}",
            f"WHY IT PLAYED OUT: {a.why_narrative}",
        ]
    )


def to_catalyst_attrs(record: CatalystRecord) -> dict:
    """Map a record to the catalyst kb_node attrs. Structural-filter keys at the TOP LEVEL
    (kb._structural_filter json_extract reads top-level only); drivers/narrative ride nested;
    retrieval_text = compose_card (the embed_text the writer passes to insert_claim)."""
    return {
        # TOP-LEVEL filter keys (kb.py:150-152 json_extract('$.<key>')).
        "type": record.catalyst_type,
        "ticker": record.ticker,
        "indication": record.indication,
        "modality": record.modality,
        "knowable_asof": record.knowable_asof,
        "event_date": record.event_date,
        # nested payload — not filtered on, carried for read-back (Plan 05).
        "drivers": {d.factor: d.value for d in record.drivers},
        "what_to_watch": record.narrative_before.what_to_watch,
        "narrative_before": record.narrative_before.model_dump(),
        "narrative_after": record.narrative_after.model_dump(),
        "retrieval_text": compose_card(record),
    }


def to_outcome_attrs(record: CatalystRecord) -> dict:
    """Map a record to the outcome kb_node attrs. The key MUST be "move" and the value the SIGNED
    decimal — the exact contract desk/builder.py:69 `_split_moves` consumes (`a["outcome"]["move"]`,
    split into up/down by sign). Never abs, never renamed."""
    return {
        "label": record.outcome_label,
        "move": record.signed_move,  # SIGNED — builder.py:69 contract
        "move_window": record.move_window,
        "confidence": record.confidence,
        "read_only": True,
    }
