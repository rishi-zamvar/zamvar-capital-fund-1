"""Quant tool library — deterministic, reproducible money-math (agents never do arithmetic).

Minimal init: re-exports only ToolResult for now. Tools import their own numpy/statsmodels
deps lazily, so importing this package stays cheap. The full tool re-export surface is wired
in Plan 08.
"""

from .result import ToolResult

__all__ = ["ToolResult"]
