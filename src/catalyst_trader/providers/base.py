"""Provider contract (Pattern 1: provenance attached, never a bare date).

Every provider function returns ``list[Catalyst]`` where each Catalyst already
carries exactly one populated ``CatalystSource`` — a date physically cannot leave
a provider without a named source (the no-LLM-date invariant is enforced at the
Catalyst model boundary). So a "provider record" *is* a Catalyst-with-source; we
alias it for documentation rather than wrap it in a redundant dataclass.
"""

from typing import Protocol

from catalyst_trader.models import Catalyst

# A Catalyst that already has its CatalystSource attached (provenance-complete).
ProviderRecord = Catalyst


class Provider(Protocol):
    """Documentation shape for every provider: fetch typed, sourced catalysts."""

    def fetch(self, tickers: list[str], date_from: str, date_to: str) -> list[Catalyst]:
        ...
