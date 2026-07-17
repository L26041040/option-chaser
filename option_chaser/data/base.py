"""Provider abstraction (spec §2.1): swap data sources by implementing this."""
from __future__ import annotations

from typing import Protocol

from ..models import ChainSnapshot


class ChainProvider(Protocol):
    def fetch_chain(self, symbol: str) -> ChainSnapshot: ...
