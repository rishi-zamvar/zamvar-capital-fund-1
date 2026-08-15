"""evidence_ref: the standardized citation format the desk mints and the verifier
resolves (CALL-04, deterministic half).

Two ref kinds, resolvable without an LLM:

  * ``kb:<node_id>``          — a KB ``EvidenceSource`` node (url + snippet_hash +
                                quote). resolve() looks it up via ``kb.get_node``.
  * ``tool:<name>#<hash>``    — a quant-tool-derived claim. The ``ToolResult.inputs``
                                snapshot IS the citation, so a tool ref is
                                *resolved-by-construction*: structurally valid
                                without any DB lookup. The hash pins the exact
                                inputs that produced the number (reproducibility).

Semantic support-checking ("does this quote actually back this claim?") is the
verifier's LLM half (Plan 06). Here we only do structural resolution + the
quote-substring gate.
"""

import hashlib
import json

from catalyst_trader import kb


def kb_ref(evidence_source_id: int) -> str:
    """Mint a ref to a KB EvidenceSource node."""
    return f"kb:{evidence_source_id}"


def _inputs_hash(inputs: dict) -> str:
    """Stable short hash of a ToolResult inputs snapshot (order-independent)."""
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def tool_ref_for(name: str, inputs: dict) -> str:
    """Mint a tool ref from a tool name + its call inputs, using the SAME stable hash
    ``tool_ref`` uses. For tool-derived claims that aren't ``ToolResult``s — e.g. KB
    ``analog_query`` / ``query_playbooks`` (they return catalyst/playbook NODE ids, not
    evidence_source ids, so they are cited by construction like any other tool, NEVER as
    ``kb:<id>``). Resolved-by-construction: the minted ref always resolves via ``resolve``."""
    return f"tool:{name}#{_inputs_hash(inputs)}"


def tool_ref(result) -> str:
    """Mint a ref for a quant-derived claim from its ToolResult (tool + inputs hash)."""
    return tool_ref_for(result.tool, result.inputs)


def resolve(conn, ref: str) -> dict | None:
    """Resolve an evidence_ref to its source payload, or None if unresolvable.

    ``kb:<id>``   -> the EvidenceSource attrs dict, or None if the node is absent
                     or isn't an evidence_source.
    ``tool:n#h``  -> a marker dict {"kind":"tool", "tool": n, "inputs_hash": h}
                     (resolved-by-construction).
    anything else -> None (the verifier drops the claim).
    """
    if ref.startswith("kb:"):
        raw = ref[len("kb:"):]
        if not raw.isdigit():
            return None
        node = kb.get_node(conn, int(raw))
        if node is None or node.get("kind") != "evidence_source":
            return None
        return node["attrs"]
    if ref.startswith("tool:") and "#" in ref:
        name, _, h = ref[len("tool:"):].partition("#")
        if not name or not h:
            return None
        return {"kind": "tool", "tool": name, "inputs_hash": h}
    return None


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def quote_supported(source_attrs: dict, claim_quote: str) -> bool:
    """True iff `claim_quote` is a substring of the source's quote, comparing
    case-insensitively with collapsed whitespace. The deterministic half of
    source-quote-or-drop."""
    quote = source_attrs.get("quote")
    if not quote or not claim_quote:
        return False
    return _normalize(claim_quote) in _normalize(quote)
