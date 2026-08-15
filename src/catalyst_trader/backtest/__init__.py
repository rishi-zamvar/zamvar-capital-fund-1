"""Backtest harness (Phase 7): point-in-time event set + pessimistic fill model.

Foundation modules the Layer-A mechanical engine (07-04) and Layer-B guarded
agentic replay (07-05) both stand on. Everything is read through the shipped
`<= as_of` guards (store.bars_asof / universe.build.universe_as_of) plus a
mandatory catalyst-verification post-filter (events.py), so a backtest can never
see data that hadn't happened — or hadn't been verified — at decision time.
"""
