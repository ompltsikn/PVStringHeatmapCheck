"""M2eAvailability submodule: hybrid inverter-level + string-proxy availability.

Spec: docs/superpowers/specs/2026-05-08-m2e-hybrid-availability-design.md
"""
from __future__ import annotations

from typing import Optional


def _classify_status(status: Optional[str], keymap: dict) -> str:
    """Map raw status string -> {"ON","DOWN","TRANSITIONAL","UNKNOWN"}.

    Match strategy: lowercase + substring.
    Priority: down > on > transitional (down menang bila ada keyword tabrakan).
    """
    if status is None:
        return "UNKNOWN"
    try:
        s = str(status).strip().lower()
    except Exception:
        return "UNKNOWN"
    if not s:
        return "UNKNOWN"

    for kw in keymap.get("down_keywords", []) or []:
        if kw and kw.lower() in s:
            return "DOWN"
    for kw in keymap.get("on_grid_keywords", []) or []:
        if kw and kw.lower() in s:
            return "ON"
    for kw in keymap.get("transitional_keywords", []) or []:
        if kw and kw.lower() in s:
            return "TRANSITIONAL"
    return "UNKNOWN"


if __name__ == "__main__":
    from pv_pipeline.availability import _classify_status

    keymap = {
        "on_grid_keywords": ["grid connected", "on-grid"],
        "down_keywords": ["shutdown", "fault"],
        "transitional_keywords": ["standby", "no sunlight"],
    }
    assert _classify_status("Grid connected", keymap) == "ON"
    assert _classify_status("Grid connected : power limited", keymap) == "ON"
    assert _classify_status("Standby :  no sunlight", keymap) == "TRANSITIONAL"
    assert _classify_status("Shutdown: command", keymap) == "DOWN"
    assert _classify_status("Mystery State", keymap) == "UNKNOWN"
    assert _classify_status(None, keymap) == "UNKNOWN"
    print("[availability] _classify_status smoke OK")
