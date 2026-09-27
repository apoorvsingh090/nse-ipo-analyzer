"""Modular data connectors (§2). All fetchers are honest about failures:
they return `Data unavailable` sentinels instead of fabricating data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..config import DATA_UNAVAILABLE


@dataclass
class DataPoint:
    value: Any
    source: str
    source_url: str | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data_type: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "value": self.value if self.value is not None else DATA_UNAVAILABLE,
            "source": self.source,
            "source_url": self.source_url,
            "observed_at": self.observed_at.isoformat(),
            "data_type": self.data_type,
        }


class BaseConnector:
    name: str = "base"
    kind: str = "third"

    def fetch(self, *args, **kwargs) -> DataPoint:  # pragma: no cover
        raise NotImplementedError

    @staticmethod
    def unavailable(reason: str = "") -> DataPoint:
        return DataPoint(value=None, source=DATA_UNAVAILABLE,
                         source_url=None, data_type=reason or "unavailable")
