"""Warm-playbook: the catalyst-record contract + narrative card + node-attr mappers.

Pure, DB-free, LLM-free. The extractor (Plan 03) emits a CatalystRecord; the KB writer (Plan 04)
maps it to catalyst/outcome node attrs + the embedded card via schema.to_*_attrs / compose_card;
generalization (Plan 05) reads the narrative fields back. kb.py is untouched (zero migration —
everything lands in attrs_json).
"""
