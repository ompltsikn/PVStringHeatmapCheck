"""M2 plugin skeleton: Severity, M2Finding, SubModule, M2Engine."""
from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    NORMAL = "NORMAL"
    INFO = "INFO"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


if __name__ == "__main__":
    from pv_pipeline.core import Severity
    assert Severity.CRITICAL.value == "CRITICAL"
    assert Severity.NORMAL.value == "NORMAL"
    assert Severity("HIGH") == Severity.HIGH
    print("[core] Severity smoke OK")
