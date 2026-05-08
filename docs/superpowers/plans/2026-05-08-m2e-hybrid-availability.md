# M2e Hybrid Availability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tambahkan submodule M2e Hybrid Availability (inverter-level + string-proxy) ke notebook PV string heatmap, sambil mendirikan skeleton plugin minimal (`M2Finding`, `Severity`, `SubModule`, `M2Engine`) untuk landing M2b–M2f berikutnya.

**Architecture:** Fase 1 menambah 4 file baru di `pv_pipeline/` (`core.py`, `availability.py`, `m2_config.py`, plus config YAML), 1 cell baru di notebook v1.4, dan extension opsional di `viz.py`. Tidak menyentuh modul Fase 0 yang sudah ada (`data_loader.py`, `transformations.py`, `string_config.py`). Output: 1 CSV summary + 1 JSONL findings per hari + (opsional) overlay heatmap.

**Tech Stack:** Python 3.10+, pandas, numpy, PyYAML (sudah ada), matplotlib + seaborn (untuk overlay opsional). Tidak ada dependency baru.

**Reference spec:** [docs/superpowers/specs/2026-05-08-m2e-hybrid-availability-design.md](../specs/2026-05-08-m2e-hybrid-availability-design.md)

**Test convention:** Mengikuti pola codebase existing (modul `pv_pipeline/*.py` tidak punya test file terpisah). Setiap modul baru mempunyai `if __name__ == "__main__":` smoke test yang dijalankan dengan `py -m pv_pipeline.<module>`. Integration test dijalankan via notebook v1.4 sel terakhir terhadap `example raw data/20260507/`.

**Working directory:** `C:\Users\nabil\Downloads\SolarYieldPro-main\kodingan pv string`. Semua path di plan ini relatif ke directory tersebut.

---

## File Map

**New files:**
- `pv_pipeline/core.py` — Severity enum, M2Finding dataclass, SubModule base, M2Engine orchestrator + writers.
- `pv_pipeline/m2_config.py` — `load_m2_config(path)` + hardcoded defaults.
- `pv_pipeline/availability.py` — `M2eAvailability(SubModule)` implementation.
- `config/m2_config.yaml` — thresholds + status keyword mapping.
- `20260507stringmap_v1.4.ipynb` — notebook baru (copy of v1.3 + Cell 4 baru).
- `outputs/` — folder dibuat runtime.

**Modified files:**
- `pv_pipeline/__init__.py` — export modul baru.
- `pv_pipeline/viz.py` — tambah parameter opsional `availability_overlay` di `plot_single_inv_heatmap` + `plot_all_inverters`.

**Untouched (Phase 0 work):**
- `pv_pipeline/data_loader.py`
- `pv_pipeline/transformations.py`
- `pv_pipeline/string_config.py`
- `config/strings.yaml`
- `20260507stringmap_v1.3.ipynb` (preserved as fallback)

---

## Task 1: Bootstrap — verify environment, create folders

**Files:**
- Create: `outputs/.gitkeep`

- [ ] **Step 1: Verify Python environment has required packages**

Run:
```
py -c "import pandas, numpy, yaml, matplotlib, seaborn; print('OK')"
```
Expected: `OK`. If ImportError on `yaml` → `py -m pip install PyYAML`.

- [ ] **Step 2: Verify raw data files exist**

Run:
```
py -c "import os; assert os.path.exists(r'example raw data\20260507\1-2.xlsx'); assert os.path.exists(r'example raw data\20260507\3-10.xlsx'); print('OK')"
```
Expected: `OK`.

- [ ] **Step 3: Create `outputs/` folder and `.gitkeep`**

Run:
```
py -c "import os; os.makedirs('outputs', exist_ok=True); open(r'outputs/.gitkeep','w').close(); print('OK')"
```
Expected: `OK`. Folder `outputs/` exists with empty `.gitkeep`.

- [ ] **Step 4: Commit**

```
git init  # bila repo belum ter-init; aman idempotent
git add outputs/.gitkeep docs/superpowers/
git commit -m "chore(m2e): bootstrap outputs folder and Phase 1 design+plan docs"
```

---

## Task 2: `pv_pipeline/core.py` — Severity enum

**Files:**
- Create: `pv_pipeline/core.py`

- [ ] **Step 1: Write smoke test scaffold**

Create file `pv_pipeline/core.py`:

```python
"""M2 plugin skeleton: Severity, M2Finding, SubModule, M2Engine."""
from __future__ import annotations


if __name__ == "__main__":
    from pv_pipeline.core import Severity
    assert Severity.CRITICAL.value == "CRITICAL"
    assert Severity.NORMAL.value == "NORMAL"
    assert Severity("HIGH") == Severity.HIGH
    print("[core] Severity smoke OK")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `py -m pv_pipeline.core`
Expected: `ImportError: cannot import name 'Severity'`.

- [ ] **Step 3: Implement Severity enum**

Replace file content with:

```python
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
```

- [ ] **Step 4: Run test, verify pass**

Run: `py -m pv_pipeline.core`
Expected: `[core] Severity smoke OK`.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/core.py
git commit -m "feat(m2e): add Severity enum in pv_pipeline.core"
```

---

## Task 3: `pv_pipeline/core.py` — M2Finding dataclass + JSONL serialization

**Files:**
- Modify: `pv_pipeline/core.py`

- [ ] **Step 1: Add failing test for M2Finding**

Append to the `if __name__ == "__main__":` block:

```python
    # M2Finding test
    from datetime import datetime
    from pv_pipeline.core import M2Finding
    f = M2Finding(
        timestamp=datetime(2026, 5, 7, 12, 0, 0),
        inverter_id="WB02-INV14",
        pv_string=None,
        sub_module="M2e_inverter",
        severity=Severity.CRITICAL,
        value=85.0,
        threshold=90.0,
        message="uptime 85% < 90%",
    )
    line = f.to_jsonl()
    assert '"severity": "CRITICAL"' in line
    assert '"timestamp": "2026-05-07T12:00:00"' in line
    assert '"pv_string": null' in line
    print("[core] M2Finding smoke OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.core`
Expected: `ImportError: cannot import name 'M2Finding'`.

- [ ] **Step 3: Implement M2Finding**

Add to `pv_pipeline/core.py` after the imports block, before the `if __name__` test:

```python
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class M2Finding:
    timestamp: datetime
    inverter_id: str
    pv_string: Optional[str]
    sub_module: str
    severity: Severity
    value: float
    threshold: float
    message: str
    extra: dict = field(default_factory=dict)

    def to_jsonl(self) -> str:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        d["severity"] = self.severity.value if isinstance(self.severity, Severity) else self.severity
        return json.dumps(d, ensure_ascii=False)
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.core`
Expected: both `[core] Severity smoke OK` and `[core] M2Finding smoke OK`.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/core.py
git commit -m "feat(m2e): add M2Finding dataclass with JSONL serialization"
```

---

## Task 4: `pv_pipeline/core.py` — SubModule base + M2Engine

**Files:**
- Modify: `pv_pipeline/core.py`

- [ ] **Step 1: Add failing test**

Append to `if __name__ == "__main__":`:

```python
    # M2Engine test
    import os
    import tempfile
    from pv_pipeline.core import SubModule, M2Engine
    import pandas as pd

    class _DummySM(SubModule):
        name = "dummy"
        def run(self, combined_df, config):
            return [
                M2Finding(
                    timestamp=datetime(2026, 5, 7, 12, 0, 0),
                    inverter_id="WB02-INV01",
                    pv_string="PV1",
                    sub_module="dummy",
                    severity=Severity.HIGH,
                    value=92.0,
                    threshold=95.0,
                    message="dummy",
                ),
            ]

    eng = M2Engine([_DummySM()])
    findings = eng.run_all(pd.DataFrame(), {})
    assert len(findings) == 1
    df = M2Engine.to_summary_df(findings)
    assert df.iloc[0]["severity"] == "HIGH"

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "f.jsonl")
        M2Engine.write_jsonl(findings, out)
        with open(out, "r", encoding="utf-8") as fp:
            lines = fp.readlines()
        assert len(lines) == 1
        assert '"severity": "HIGH"' in lines[0]
    print("[core] M2Engine smoke OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.core`
Expected: `ImportError: cannot import name 'SubModule'`.

- [ ] **Step 3: Implement SubModule + M2Engine**

Append to `pv_pipeline/core.py` after `M2Finding`:

```python
from typing import Iterable, List
import pandas as pd


class SubModule:
    """Base class for M2 submodules. Override `run()`."""
    name: str = "base"

    def run(self, combined_df: pd.DataFrame, config: dict) -> List[M2Finding]:
        raise NotImplementedError


class M2Engine:
    """Minimal orchestrator: jalankan list of SubModule, kumpulkan findings."""

    def __init__(self, submodules: Iterable[SubModule]):
        self.submodules = list(submodules)

    def run_all(self, combined_df: pd.DataFrame, config: dict) -> List[M2Finding]:
        findings: List[M2Finding] = []
        for sm in self.submodules:
            findings.extend(sm.run(combined_df, config))
        return findings

    @staticmethod
    def write_jsonl(findings: List[M2Finding], path: str) -> None:
        with open(path, "w", encoding="utf-8") as fp:
            for fin in findings:
                fp.write(fin.to_jsonl() + "\n")

    @staticmethod
    def to_summary_df(findings: List[M2Finding]) -> pd.DataFrame:
        rows = []
        for f in findings:
            d = asdict(f)
            d["severity"] = f.severity.value if isinstance(f.severity, Severity) else f.severity
            d["timestamp"] = f.timestamp.isoformat() if f.timestamp else None
            rows.append(d)
        return pd.DataFrame(rows)
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.core`
Expected: all three smoke prints (`Severity`, `M2Finding`, `M2Engine`).

- [ ] **Step 5: Commit**

```
git add pv_pipeline/core.py
git commit -m "feat(m2e): add SubModule base and M2Engine orchestrator"
```

---

## Task 5: `pv_pipeline/m2_config.py` — config loader with defaults

**Files:**
- Create: `pv_pipeline/m2_config.py`

- [ ] **Step 1: Write failing smoke test scaffold**

Create `pv_pipeline/m2_config.py`:

```python
"""M2 thresholds + keyword mapping config loader."""
from __future__ import annotations


if __name__ == "__main__":
    from pv_pipeline.m2_config import DEFAULT_M2_CONFIG, load_m2_config
    cfg = load_m2_config("nonexistent_path.yaml")
    assert cfg["m2e"]["severity_thresholds"]["critical_below"] == 90
    assert "grid connected" in cfg["m2e"]["inverter_status_map"]["on_grid_keywords"]
    assert cfg["m2e"]["string_proxy"]["pstr_zero_threshold_kw"] == 0.1
    print("[m2_config] defaults smoke OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.m2_config`
Expected: `ImportError: cannot import name 'load_m2_config'`.

- [ ] **Step 3: Implement defaults + loader**

Replace file content:

```python
"""M2 thresholds + keyword mapping config loader.

Lifecycle terpisah dari ``string_config.py`` (yang urus EMPTY_PV_MAP):
- ``string_config`` = peta string fisik, jarang berubah.
- ``m2_config`` = threshold analitik, sering di-tune.
"""
from __future__ import annotations

import copy
import os
import warnings
from typing import Any, Dict


DEFAULT_M2_CONFIG: Dict[str, Any] = {
    "m2e": {
        "inverter_status_map": {
            "on_grid_keywords": ["grid connected", "on-grid", "on grid", "ongrid"],
            "down_keywords": ["shutdown", "fault", "stopped", "stop", "error"],
            "transitional_keywords": [
                "standby",
                "starting",
                "stopping",
                "initializing",
                "initialization",
                "detecting",
                "detection",
                "no sunlight",
            ],
        },
        "shutdown_time_detection": "auto",
        "string_proxy": {
            "pstr_zero_threshold_kw": 0.1,
            "sibling_median_active_kw": 1.0,
            "min_active_siblings_pct": 50,
            "debounce_consecutive_steps": 2,
        },
        "severity_thresholds": {
            "critical_below": 90,
            "high_below": 95,
            "medium_below": 97,
            "info_below": 99,
            "emit_normal": False,
        },
        "output_dir": "outputs",
        "show_overlay": False,
    },
}


def _ensure_yaml() -> None:
    try:
        import yaml  # noqa: F401
    except ImportError:
        import subprocess
        import sys
        print("Installing missing package: PyYAML")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyYAML"])


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursive merge override into a copy of base. override wins."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_m2_config(path: str) -> Dict[str, Any]:
    """Load YAML config, merge atas DEFAULT_M2_CONFIG.

    Bila ``path`` tidak ada, return defaults + warning (tidak raise).
    """
    if not path or not os.path.exists(path):
        warnings.warn(
            f"[m2_config] {path!r} not found, using DEFAULT_M2_CONFIG",
            stacklevel=2,
        )
        return copy.deepcopy(DEFAULT_M2_CONFIG)

    _ensure_yaml()
    import yaml  # noqa: WPS433

    with open(path, "r", encoding="utf-8") as fp:
        user_cfg = yaml.safe_load(fp) or {}

    return _deep_merge(DEFAULT_M2_CONFIG, user_cfg)


if __name__ == "__main__":
    from pv_pipeline.m2_config import DEFAULT_M2_CONFIG, load_m2_config
    cfg = load_m2_config("nonexistent_path.yaml")
    assert cfg["m2e"]["severity_thresholds"]["critical_below"] == 90
    assert "grid connected" in cfg["m2e"]["inverter_status_map"]["on_grid_keywords"]
    assert cfg["m2e"]["string_proxy"]["pstr_zero_threshold_kw"] == 0.1
    print("[m2_config] defaults smoke OK")
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.m2_config`
Expected: warning + `[m2_config] defaults smoke OK`.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/m2_config.py
git commit -m "feat(m2e): add load_m2_config with deep-merge defaults"
```

---

## Task 6: `config/m2_config.yaml` — concrete config file

**Files:**
- Create: `config/m2_config.yaml`

- [ ] **Step 1: Add failing smoke test in m2_config.py**

Append to `if __name__ == "__main__":` in `pv_pipeline/m2_config.py`:

```python
    # YAML round-trip test
    cfg2 = load_m2_config("config/m2_config.yaml")
    assert cfg2["m2e"]["severity_thresholds"]["critical_below"] == 90
    assert "grid connected" in cfg2["m2e"]["inverter_status_map"]["on_grid_keywords"]
    print("[m2_config] yaml round-trip OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.m2_config`
Expected: warning bahwa `config/m2_config.yaml` not found, only first smoke message printed.

- [ ] **Step 3: Create `config/m2_config.yaml`**

Create file with content:

```yaml
# Fase 1 — M2e Hybrid Availability config
# Edited: 2026-05-08 (initial)
m2e:
  inverter_status_map:
    # Substring match (lowercased) terhadap nilai kolom 'Inverter status'.
    # Nilai di luar mapping akan diberi warning + dianggap UNKNOWN.
    on_grid_keywords:      ["grid connected", "on-grid", "on grid", "ongrid"]
    down_keywords:         ["shutdown", "fault", "stopped", "stop", "error"]
    transitional_keywords: ["standby", "starting", "stopping",
                            "initializing", "initialization",
                            "detecting", "detection", "no sunlight"]

  # auto | event | cumulative | status_only
  shutdown_time_detection: "auto"

  string_proxy:
    pstr_zero_threshold_kw:     0.1
    sibling_median_active_kw:   1.0
    min_active_siblings_pct:    50
    debounce_consecutive_steps: 2

  severity_thresholds:
    critical_below: 90
    high_below:     95
    medium_below:   97
    info_below:     99
    emit_normal:    false

  output_dir: "outputs"
  show_overlay:  false
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.m2_config`
Expected: `[m2_config] defaults smoke OK` and `[m2_config] yaml round-trip OK` (no warning).

- [ ] **Step 5: Commit**

```
git add config/m2_config.yaml pv_pipeline/m2_config.py
git commit -m "feat(m2e): add config/m2_config.yaml with Phase 1 defaults"
```

---

## Task 7: `pv_pipeline/availability.py` — Step 1 (status mapping helper)

**Files:**
- Create: `pv_pipeline/availability.py`

- [ ] **Step 1: Write failing test scaffold**

Create `pv_pipeline/availability.py`:

```python
"""M2eAvailability submodule: hybrid inverter-level + string-proxy availability.

Spec: docs/superpowers/specs/2026-05-08-m2e-hybrid-availability-design.md
"""
from __future__ import annotations


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
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.availability`
Expected: `ImportError: cannot import name '_classify_status'`.

- [ ] **Step 3: Implement `_classify_status`**

Replace file content (keeping smoke test at bottom):

```python
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
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.availability`
Expected: `[availability] _classify_status smoke OK`.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/availability.py
git commit -m "feat(m2e): add _classify_status keyword-based mapper"
```

---

## Task 8: `pv_pipeline/availability.py` — Step 2 (auto-detect shutdown_time mode)

**Files:**
- Modify: `pv_pipeline/availability.py`

- [ ] **Step 1: Add failing test**

Append BEFORE the final `print` in the `if __name__ == "__main__":` block:

```python
    # _detect_shutdown_time_mode test
    import pandas as pd
    from pv_pipeline.availability import _detect_shutdown_time_mode

    s_dt = pd.Series(["2026/05/06 18:26:40", "2026/05/06 18:21:02", "-", "2026/05/06 18:25:01"])
    s_st = pd.Series(["2026/05/06 06:08:46", "2026/05/06 06:08:48", "-", "2026/05/06 06:09:03"])
    mode, sd_dt, st_dt = _detect_shutdown_time_mode(s_dt, s_st, force=None)
    assert mode == "EVENT", f"expected EVENT got {mode}"
    assert sd_dt.notna().sum() == 3
    assert st_dt.notna().sum() == 3

    s_empty = pd.Series([None, None, None])
    mode2, _, _ = _detect_shutdown_time_mode(s_empty, s_empty, force=None)
    assert mode2 == "STATUS_ONLY"

    mode3, _, _ = _detect_shutdown_time_mode(s_dt, s_st, force="status_only")
    assert mode3 == "STATUS_ONLY"
    print("[availability] _detect_shutdown_time_mode smoke OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.availability`
Expected: `ImportError: cannot import name '_detect_shutdown_time_mode'`.

- [ ] **Step 3: Implement `_detect_shutdown_time_mode`**

Add to top of `pv_pipeline/availability.py` after the `from typing import Optional` line:

```python
import numpy as np
import pandas as pd
from typing import Tuple


_SENTINEL_NULLS = {"-", "", "nan", "NaN", "None"}


def _replace_sentinels(s: "pd.Series") -> "pd.Series":
    """Ganti literal sentinel ('-', '', 'nan', dst.) dengan NaN."""
    if s is None:
        return s
    return s.where(~s.astype(str).str.strip().isin(_SENTINEL_NULLS), other=np.nan)


def _detect_shutdown_time_mode(
    shutdown_series: "pd.Series",
    startup_series: "pd.Series",
    force: Optional[str] = None,
) -> Tuple[str, "pd.Series", "pd.Series"]:
    """Auto-detect dtype mode for shutdown/startup time columns.

    Returns (mode, shutdown_parsed, startup_parsed) where mode ∈
    {"EVENT","CUMULATIVE","STATUS_ONLY"}.

    `force`:
        - None / "auto": auto-detect.
        - "event" / "cumulative" / "status_only": skip detection.
    """
    if force and force.lower() != "auto":
        f = force.lower()
        if f == "event":
            sd = pd.to_datetime(_replace_sentinels(shutdown_series), errors="coerce")
            st = pd.to_datetime(_replace_sentinels(startup_series), errors="coerce")
            return "EVENT", sd, st
        if f == "cumulative":
            sd = pd.to_numeric(_replace_sentinels(shutdown_series), errors="coerce")
            st = pd.to_numeric(_replace_sentinels(startup_series), errors="coerce")
            return "CUMULATIVE", sd, st
        if f == "status_only":
            return "STATUS_ONLY", shutdown_series, startup_series

    sd_clean = _replace_sentinels(shutdown_series) if shutdown_series is not None else None
    st_clean = _replace_sentinels(startup_series) if startup_series is not None else None
    if sd_clean is None or st_clean is None:
        return "STATUS_ONLY", shutdown_series, startup_series

    n = len(sd_clean)
    if n == 0:
        return "STATUS_ONLY", shutdown_series, startup_series

    # Try EVENT
    sd_dt = pd.to_datetime(sd_clean, errors="coerce")
    st_dt = pd.to_datetime(st_clean, errors="coerce")
    ratio_event = (sd_dt.notna().sum() + st_dt.notna().sum()) / (2 * n)
    if ratio_event >= 0.80:
        return "EVENT", sd_dt, st_dt

    # Try CUMULATIVE
    sd_num = pd.to_numeric(sd_clean, errors="coerce")
    st_num = pd.to_numeric(st_clean, errors="coerce")
    ratio_num = (sd_num.notna().sum() + st_num.notna().sum()) / (2 * n)
    if ratio_num >= 0.80:
        return "CUMULATIVE", sd_num, st_num

    return "STATUS_ONLY", shutdown_series, startup_series
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.availability`
Expected: both `_classify_status` and `_detect_shutdown_time_mode` smoke prints.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/availability.py
git commit -m "feat(m2e): add shutdown_time auto-detect with sentinel cleaning"
```

---

## Task 9: `pv_pipeline/availability.py` — `_severity_for_uptime`

**Files:**
- Modify: `pv_pipeline/availability.py`

- [ ] **Step 1: Add failing test**

Append to `if __name__ == "__main__":`:

```python
    # _severity_for_uptime test
    from pv_pipeline.availability import _severity_for_uptime
    from pv_pipeline.core import Severity

    th = {"critical_below": 90, "high_below": 95, "medium_below": 97, "info_below": 99}
    assert _severity_for_uptime(85.0, th) == (Severity.CRITICAL, 90)
    assert _severity_for_uptime(92.0, th) == (Severity.HIGH, 95)
    assert _severity_for_uptime(96.5, th) == (Severity.MEDIUM, 97)
    assert _severity_for_uptime(98.0, th) == (Severity.INFO, 99)
    assert _severity_for_uptime(99.5, th) == (Severity.NORMAL, 99)
    assert _severity_for_uptime(float("nan"), th)[0] == Severity.NORMAL
    print("[availability] _severity_for_uptime smoke OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.availability`
Expected: `ImportError: cannot import name '_severity_for_uptime'`.

- [ ] **Step 3: Implement `_severity_for_uptime`**

Add to `pv_pipeline/availability.py` after `_detect_shutdown_time_mode`:

```python
from pv_pipeline.core import Severity


def _severity_for_uptime(uptime_pct: float, thresholds: dict) -> Tuple[Severity, float]:
    """Map uptime_pct -> (Severity, threshold_breached). NaN -> (NORMAL, NaN)."""
    if uptime_pct is None:
        return Severity.NORMAL, float("nan")
    try:
        v = float(uptime_pct)
    except Exception:
        return Severity.NORMAL, float("nan")
    if v != v:  # NaN
        return Severity.NORMAL, float("nan")

    if v < float(thresholds.get("critical_below", 90)):
        return Severity.CRITICAL, float(thresholds.get("critical_below", 90))
    if v < float(thresholds.get("high_below", 95)):
        return Severity.HIGH, float(thresholds.get("high_below", 95))
    if v < float(thresholds.get("medium_below", 97)):
        return Severity.MEDIUM, float(thresholds.get("medium_below", 97))
    if v < float(thresholds.get("info_below", 99)):
        return Severity.INFO, float(thresholds.get("info_below", 99))
    return Severity.NORMAL, float(thresholds.get("info_below", 99))
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.availability`
Expected: `_severity_for_uptime` smoke OK.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/availability.py
git commit -m "feat(m2e): add _severity_for_uptime mapper"
```

---

## Task 10: `pv_pipeline/availability.py` — `_compute_inverter_availability`

**Files:**
- Modify: `pv_pipeline/availability.py`

- [ ] **Step 1: Add failing test**

Append to `if __name__ == "__main__":`:

```python
    # _compute_inverter_availability test
    from pv_pipeline.availability import _compute_inverter_availability

    df_test = pd.DataFrame({
        "Inverter_ID": ["WB02-INV01"]*12 + ["WB02-INV02"]*12,
        "Start Time": list(pd.date_range("2026-05-07 06:00", periods=12, freq="5min"))*2,
        "_status_class": (
            ["ON"]*8 + ["DOWN"]*4   # INV01 -> uptime 8/12 = 66.67% -> CRITICAL
            + ["ON"]*12              # INV02 -> uptime 100% -> NORMAL (skipped)
        ),
    })
    cfg = {
        "severity_thresholds": {"critical_below": 90, "high_below": 95,
                                "medium_below": 97, "info_below": 99,
                                "emit_normal": False},
    }
    findings = _compute_inverter_availability(df_test, mode="STATUS_ONLY", cfg=cfg,
                                              interval_minutes=5)
    assert len(findings) == 1, f"expected 1 finding, got {len(findings)}"
    f0 = findings[0]
    assert f0.inverter_id == "WB02-INV01"
    assert f0.severity.value == "CRITICAL"
    assert abs(f0.value - 66.6667) < 0.01
    assert f0.extra["downtime_minutes"] == 20
    print("[availability] _compute_inverter_availability smoke OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.availability`
Expected: `ImportError: cannot import name '_compute_inverter_availability'`.

- [ ] **Step 3: Implement function**

Add to `pv_pipeline/availability.py` after `_severity_for_uptime`:

```python
from datetime import datetime
from pv_pipeline.core import M2Finding


def _compute_inverter_availability(
    df: "pd.DataFrame",
    mode: str,
    cfg: dict,
    interval_minutes: float,
    sd_parsed: Optional["pd.Series"] = None,
    st_parsed: Optional["pd.Series"] = None,
) -> list:
    """Compute per-inverter daily uptime% + emit M2Finding(s).

    `df` harus berisi kolom: Inverter_ID, Start Time, _status_class.
    Untuk mode EVENT, opsional pass `sd_parsed`/`st_parsed` (datetime series
    aligned to df index) untuk hitung downtime_minutes lebih akurat;
    fallback selalu n_down × interval_minutes.
    """
    th = cfg.get("severity_thresholds", {})
    emit_normal = bool(th.get("emit_normal", False))

    findings = []
    for inv_id, sub in df.groupby("Inverter_ID", sort=True):
        n_on = int((sub["_status_class"] == "ON").sum())
        n_down = int((sub["_status_class"] == "DOWN").sum())
        denom = n_on + n_down

        if denom == 0:
            continue

        uptime_pct = 100.0 * n_on / denom

        downtime_min = float(n_down) * float(interval_minutes)
        if mode == "EVENT" and sd_parsed is not None and st_parsed is not None:
            try:
                sd_sub = sd_parsed.loc[sub.index]
                st_sub = st_parsed.loc[sub.index]
                ev_down = (sd_sub > st_sub) & sd_sub.notna() & st_sub.notna()
                if ev_down.any():
                    down_rows = sub.loc[ev_down, "Start Time"]
                    if len(down_rows) >= 2:
                        delta_min = (down_rows.max() - down_rows.min()).total_seconds() / 60.0
                        downtime_min = float(max(downtime_min, delta_min))
            except Exception:
                pass

        sev, threshold = _severity_for_uptime(uptime_pct, th)
        if sev == Severity.NORMAL and not emit_normal:
            continue

        ts_min = sub["Start Time"].min()
        ts_dt = ts_min.to_pydatetime() if hasattr(ts_min, "to_pydatetime") else ts_min

        findings.append(M2Finding(
            timestamp=ts_dt if isinstance(ts_dt, datetime) else datetime.utcnow(),
            inverter_id=str(inv_id),
            pv_string=None,
            sub_module="M2e_inverter",
            severity=sev,
            value=round(uptime_pct, 4),
            threshold=threshold,
            message=f"inverter uptime {uptime_pct:.2f}% (n_on={n_on}, n_down={n_down})",
            extra={
                "n_on": n_on,
                "n_down": n_down,
                "downtime_minutes": round(downtime_min, 2),
                "mode": mode,
            },
        ))

    return findings
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.availability`
Expected: `_compute_inverter_availability` smoke OK.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/availability.py
git commit -m "feat(m2e): add _compute_inverter_availability with severity emission"
```

---

## Task 11: `pv_pipeline/availability.py` — `_compute_string_proxy`

**Files:**
- Modify: `pv_pipeline/availability.py`

- [ ] **Step 1: Add failing test**

Append to `if __name__ == "__main__":`:

```python
    # _compute_string_proxy test
    from pv_pipeline.availability import _compute_string_proxy

    times = list(pd.date_range("2026-05-07 10:00", periods=6, freq="5min"))
    rows = []
    # INV01: PV1 stuck di 0 selama semua row, sibling sehat
    for t in times:
        rows.append({"Inverter_ID": "WB02-INV01", "Start Time": t, "_status_class": "ON",
                     "PV1 Power(kW)": 0.0, "PV2 Power(kW)": 5.0,
                     "PV3 Power(kW)": 5.5, "PV4 Power(kW)": 4.8})
    # INV02 sibling reference: semua PV ~5 kW
    for t in times:
        rows.append({"Inverter_ID": "WB02-INV02", "Start Time": t, "_status_class": "ON",
                     "PV1 Power(kW)": 5.0, "PV2 Power(kW)": 5.0,
                     "PV3 Power(kW)": 5.5, "PV4 Power(kW)": 4.8})
    df_test = pd.DataFrame(rows)
    pv_cols = ["PV1 Power(kW)", "PV2 Power(kW)", "PV3 Power(kW)", "PV4 Power(kW)"]

    cfg = {
        "string_proxy": {
            "pstr_zero_threshold_kw": 0.1,
            "sibling_median_active_kw": 1.0,
            "min_active_siblings_pct": 50,
            "debounce_consecutive_steps": 2,
        },
        "severity_thresholds": {"critical_below": 90, "high_below": 95,
                                "medium_below": 97, "info_below": 99,
                                "emit_normal": False},
    }
    findings = _compute_string_proxy(df_test, pv_cols=pv_cols, cfg=cfg, interval_minutes=5)
    assert len(findings) == 1, f"expected 1 string-proxy finding, got {len(findings)}"
    f0 = findings[0]
    assert f0.inverter_id == "WB02-INV01"
    assert f0.pv_string == "PV1"
    assert f0.severity.value in {"CRITICAL", "HIGH", "MEDIUM", "INFO"}
    assert f0.extra["n_events"] >= 1
    print("[availability] _compute_string_proxy smoke OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.availability`
Expected: `ImportError: cannot import name '_compute_string_proxy'`.

- [ ] **Step 3: Implement function**

Add to `pv_pipeline/availability.py` after `_compute_inverter_availability`:

```python
import re

_PV_NUM_RE = re.compile(r"PV\s*0*?(\d+)\s+Power\(kW\)", flags=re.I)


def _label_to_pv_name(label: str) -> str:
    """`PV3 Power(kW)` -> `PV3` ; fallback ke label asli."""
    m = _PV_NUM_RE.search(label)
    return f"PV{int(m.group(1))}" if m else label


def _compute_string_proxy(
    df: "pd.DataFrame",
    pv_cols: list,
    cfg: dict,
    interval_minutes: float,
) -> list:
    """Detect string proxy-down events.

    `df` harus berisi: Inverter_ID, Start Time, _status_class, kolom-kolom di pv_cols.
    """
    sp = cfg.get("string_proxy", {})
    th = cfg.get("severity_thresholds", {})
    emit_normal = bool(th.get("emit_normal", False))
    p_zero = float(sp.get("pstr_zero_threshold_kw", 0.1))
    sib_med_th = float(sp.get("sibling_median_active_kw", 1.0))
    min_act_pct = float(sp.get("min_active_siblings_pct", 50))
    debounce = int(sp.get("debounce_consecutive_steps", 2))

    daylight_ts = set(
        df.loc[df["_status_class"] == "ON", "Start Time"].dropna().unique()
    )
    if not daylight_ts:
        return []

    findings: list = []
    n_pv_total = len(pv_cols)

    for inv_id, sub in df.groupby("Inverter_ID", sort=True):
        sub = sub.sort_values("Start Time").reset_index(drop=True)
        on_mask = (sub["_status_class"] == "ON") & sub["Start Time"].isin(daylight_ts)
        sub_on = sub[on_mask]
        if sub_on.empty:
            continue

        daylight_minutes_inv = float(len(sub_on)) * float(interval_minutes)

        pv_vals = sub_on[pv_cols].astype(float)
        sib_median = pv_vals.median(axis=1, skipna=True)
        active_count = (pv_vals > p_zero).sum(axis=1)
        active_pct = 100.0 * active_count / max(n_pv_total, 1)
        qualified = (sib_median >= sib_med_th) & (active_pct >= min_act_pct)

        for pv_col in pv_cols:
            pv_name = _label_to_pv_name(pv_col)
            pv_series = pv_vals[pv_col]
            cand = qualified & (pv_series < p_zero)
            if not cand.any():
                continue

            cand_arr = cand.to_numpy()
            run_lens = []
            run_start_idx = None
            for i, v in enumerate(cand_arr):
                if v:
                    if run_start_idx is None:
                        run_start_idx = i
                else:
                    if run_start_idx is not None:
                        run_lens.append((run_start_idx, i - 1))
                        run_start_idx = None
            if run_start_idx is not None:
                run_lens.append((run_start_idx, len(cand_arr) - 1))

            qualified_runs = [(a, b) for (a, b) in run_lens if (b - a + 1) >= debounce]
            if not qualified_runs:
                continue

            event_minutes_total = sum(
                (b - a + 1) * float(interval_minutes) for (a, b) in qualified_runs
            )
            string_uptime_pct = max(
                0.0,
                100.0 - 100.0 * event_minutes_total / max(daylight_minutes_inv, 1e-9),
            )
            sev, threshold = _severity_for_uptime(string_uptime_pct, th)
            if sev == Severity.NORMAL and not emit_normal:
                continue

            ts_first = sub_on["Start Time"].iloc[qualified_runs[0][0]]
            ts_last = sub_on["Start Time"].iloc[qualified_runs[-1][1]]
            ts_dt = ts_first.to_pydatetime() if hasattr(ts_first, "to_pydatetime") else ts_first

            findings.append(M2Finding(
                timestamp=ts_dt if isinstance(ts_dt, datetime) else datetime.utcnow(),
                inverter_id=str(inv_id),
                pv_string=pv_name,
                sub_module="M2e_string_proxy",
                severity=sev,
                value=round(string_uptime_pct, 4),
                threshold=threshold,
                message=(
                    f"{inv_id} {pv_name} proxy-down "
                    f"{event_minutes_total:.0f}min/{daylight_minutes_inv:.0f}min daylight "
                    f"({string_uptime_pct:.2f}% uptime)"
                ),
                extra={
                    "event_minutes": round(event_minutes_total, 2),
                    "daylight_minutes": round(daylight_minutes_inv, 2),
                    "n_events": len(qualified_runs),
                    "first_event_ts": ts_first.isoformat() if hasattr(ts_first, "isoformat") else str(ts_first),
                    "last_event_ts": ts_last.isoformat() if hasattr(ts_last, "isoformat") else str(ts_last),
                },
            ))

    return findings
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.availability`
Expected: `_compute_string_proxy` smoke OK.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/availability.py
git commit -m "feat(m2e): add _compute_string_proxy with debounce + daylight proxy"
```

---

## Task 12: `pv_pipeline/availability.py` — `M2eAvailability.run()` orchestration

**Files:**
- Modify: `pv_pipeline/availability.py`

- [ ] **Step 1: Add failing end-to-end test**

Append to `if __name__ == "__main__":`:

```python
    # M2eAvailability.run() end-to-end smoke
    from pv_pipeline.availability import M2eAvailability

    times = list(pd.date_range("2026-05-07 10:00", periods=6, freq="5min"))
    rows = []
    for t in times:
        rows.append({"ManageObject": "x/Inv_A_201_IKN", "Inverter_ID": "WB02-INV01",
                     "Start Time": t, "Inverter status": "Grid connected",
                     "Inverter shutdown time": "-", "Inverter startup time": "-",
                     "PV1 Power(kW)": 0.0, "PV2 Power(kW)": 5.0,
                     "PV3 Power(kW)": 5.5, "PV4 Power(kW)": 4.8})
    for t in times:
        rows.append({"ManageObject": "x/Inv_A_202_IKN", "Inverter_ID": "WB02-INV02",
                     "Start Time": t, "Inverter status": "Grid connected",
                     "Inverter shutdown time": "-", "Inverter startup time": "-",
                     "PV1 Power(kW)": 5.0, "PV2 Power(kW)": 5.0,
                     "PV3 Power(kW)": 5.5, "PV4 Power(kW)": 4.8})
    df_e2e = pd.DataFrame(rows)

    from pv_pipeline.m2_config import DEFAULT_M2_CONFIG
    sm = M2eAvailability()
    res = sm.run(df_e2e, DEFAULT_M2_CONFIG)
    assert isinstance(res, list)
    sub_string = [f for f in res if f.sub_module == "M2e_string_proxy"]
    assert len(sub_string) == 1
    assert sub_string[0].pv_string == "PV1"
    print("[availability] M2eAvailability.run() smoke OK")
```

- [ ] **Step 2: Run, verify failure**

Run: `py -m pv_pipeline.availability`
Expected: `ImportError: cannot import name 'M2eAvailability'`.

- [ ] **Step 3: Implement `M2eAvailability` class + helpers**

Add to `pv_pipeline/availability.py` (after `_compute_string_proxy`, before the `if __name__` block):

```python
import warnings
from pv_pipeline.core import SubModule


_PV_POWER_COL_RE = re.compile(r"PV\s*0*?(\d+)\s+Power\(kW\)", flags=re.I)


def _detect_pv_power_cols(df: "pd.DataFrame", pv_max_allowed: int = 28) -> list:
    cols = [c for c in df.columns if _PV_POWER_COL_RE.search(str(c))]
    out = []
    for c in cols:
        m = _PV_POWER_COL_RE.search(str(c))
        if m and int(m.group(1)) <= pv_max_allowed:
            out.append(c)
    out.sort(key=lambda x: int(_PV_POWER_COL_RE.search(x).group(1)))
    return out


def _estimate_interval_minutes(start_times: "pd.Series") -> float:
    s = pd.to_datetime(start_times, errors="coerce").dropna().sort_values()
    if len(s) < 2:
        return 5.0
    diffs = s.diff().dropna().dt.total_seconds() / 60.0
    if len(diffs) == 0:
        return 5.0
    med = float(diffs.median())
    if med <= 0 or med != med:
        return 5.0
    return med


class M2eAvailability(SubModule):
    """Hybrid M2e: inverter-level + string-proxy availability."""
    name = "M2e_hybrid"

    def run(self, combined_df: "pd.DataFrame", config: dict) -> list:
        cfg = (config or {}).get("m2e", {}) or {}

        required = ["Inverter_ID", "Start Time", "Inverter status"]
        missing = [c for c in required if c not in combined_df.columns]
        if missing:
            warnings.warn(f"[M2e] missing required columns {missing}; skipping submodule")
            return []

        df = combined_df.copy()
        df["Start Time"] = pd.to_datetime(df["Start Time"], errors="coerce")

        keymap = cfg.get("inverter_status_map", {}) or {}
        df["_status_class"] = df["Inverter status"].apply(lambda s: _classify_status(s, keymap))
        unknown_mask = df["_status_class"] == "UNKNOWN"
        if unknown_mask.any():
            unk = df.loc[unknown_mask, "Inverter status"].astype(str).value_counts().head(20)
            warnings.warn(f"[M2e] UNKNOWN status values (top 20):\n{unk.to_string()}")

        force = (cfg.get("shutdown_time_detection") or "auto")
        sd_col = df["Inverter shutdown time"] if "Inverter shutdown time" in df.columns else None
        st_col = df["Inverter startup time"] if "Inverter startup time" in df.columns else None
        if sd_col is None or st_col is None:
            mode, sd_parsed, st_parsed = "STATUS_ONLY", None, None
        else:
            mode, sd_parsed, st_parsed = _detect_shutdown_time_mode(sd_col, st_col, force=force)
        print(f"[M2e] shutdown_time mode = {mode}")

        interval_min = _estimate_interval_minutes(df["Start Time"])
        inv_findings = _compute_inverter_availability(
            df, mode=mode, cfg=cfg, interval_minutes=interval_min,
            sd_parsed=sd_parsed, st_parsed=st_parsed,
        )

        pv_cols = _detect_pv_power_cols(df, pv_max_allowed=28)
        if not pv_cols:
            warnings.warn("[M2e] no PV power columns found; skipping string-proxy")
            str_findings = []
        else:
            str_findings = _compute_string_proxy(
                df, pv_cols=pv_cols, cfg=cfg, interval_minutes=interval_min,
            )

        return inv_findings + str_findings
```

- [ ] **Step 4: Run, verify pass**

Run: `py -m pv_pipeline.availability`
Expected: `[M2e] shutdown_time mode = STATUS_ONLY` (sentinel-only) and `[availability] M2eAvailability.run() smoke OK`.

- [ ] **Step 5: Commit**

```
git add pv_pipeline/availability.py
git commit -m "feat(m2e): wire M2eAvailability.run() pipeline (status->mode->inverter->string)"
```

---

## Task 13: `pv_pipeline/__init__.py` — export new modules

**Files:**
- Modify: `pv_pipeline/__init__.py`

- [ ] **Step 1: Add failing import test**

Run:
```
py -c "import pv_pipeline; assert hasattr(pv_pipeline,'core'); assert hasattr(pv_pipeline,'availability'); assert hasattr(pv_pipeline,'m2_config'); print('OK')"
```
Expected: `AssertionError`.

- [ ] **Step 2: Update `pv_pipeline/__init__.py`**

Replace content:

```python
"""PV string-level performance analysis pipeline.

Phase 0 modules (refactor)
--------------------------
- data_loader : Google Drive download (gdown) + Excel ingestion utilities.
- transformations : ManageObject -> Inverter_ID, PV power computation, pivot helpers.
- string_config : Load and sanitize EMPTY_PV_MAP from YAML.
- viz : Per-inverter heatmap rendering (matplotlib + seaborn).

Phase 1 modules (M2e Hybrid Availability)
-----------------------------------------
- core : Severity, M2Finding, SubModule, M2Engine skeleton.
- m2_config : Load thresholds + status keyword mapping.
- availability : M2eAvailability submodule (inverter-level + string-proxy).
"""

__version__ = "0.2.0"

from . import (
    data_loader,
    transformations,
    string_config,
    viz,
    core,
    m2_config,
    availability,
)

__all__ = [
    "data_loader", "transformations", "string_config", "viz",
    "core", "m2_config", "availability",
]
```

- [ ] **Step 3: Run, verify pass**

Run:
```
py -c "import pv_pipeline; assert hasattr(pv_pipeline,'core'); assert hasattr(pv_pipeline,'availability'); assert hasattr(pv_pipeline,'m2_config'); print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```
git add pv_pipeline/__init__.py
git commit -m "feat(m2e): export core, m2_config, availability from pv_pipeline"
```

---

## Task 14: `pv_pipeline/viz.py` — opsional availability overlay

**Files:**
- Modify: `pv_pipeline/viz.py`

Backward compatibility: parameter baru OPTIONAL dengan default `None` → output identik v1.3 bila tidak diset.

- [ ] **Step 1: Add failing signature test**

Run:
```
py -c "from pv_pipeline.viz import plot_single_inv_heatmap; import inspect; sig=inspect.signature(plot_single_inv_heatmap); assert 'availability_overlay' in sig.parameters, 'param missing'; print('OK')"
```
Expected: `AssertionError: param missing`.

- [ ] **Step 2: Modify `plot_single_inv_heatmap` signature**

In `pv_pipeline/viz.py`, find the signature of `plot_single_inv_heatmap`. Replace:

```python
def plot_single_inv_heatmap(
    inv_id: str,
    df: pd.DataFrame,
    pv_max_allowed: int = PV_MAX_ALLOWED_DEFAULT,
    cell_size: float = CELL_SIZE_DEFAULT,
    show: bool = True,
    close_after_show: bool = False,
    empty_pv_map: Optional[Dict[str, List[int]]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
```

With:

```python
def plot_single_inv_heatmap(
    inv_id: str,
    df: pd.DataFrame,
    pv_max_allowed: int = PV_MAX_ALLOWED_DEFAULT,
    cell_size: float = CELL_SIZE_DEFAULT,
    show: bool = True,
    close_after_show: bool = False,
    empty_pv_map: Optional[Dict[str, List[int]]] = None,
    availability_overlay: Optional[Dict[str, object]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
```

- [ ] **Step 3: Add overlay rendering before `plt.tight_layout()`**

In `pv_pipeline/viz.py`, find `plt.tight_layout()` near the end of `plot_single_inv_heatmap`. Insert this block BEFORE it:

```python
    if availability_overlay:
        try:
            inv_status_per_ts = availability_overlay.get("inv_status_per_ts", {})
            proxy_down_cells = availability_overlay.get("proxy_down_cells", set())
            ts_index = list(pivot_plot.columns)
            for ci, ts in enumerate(ts_index):
                cls = inv_status_per_ts.get((inv_id, ts), "UNKNOWN")
                if cls != "ON":
                    rect = Rectangle((ci, 0), 1, n_pv,
                                     facecolor="gray", alpha=0.25, edgecolor="none",
                                     zorder=4)
                    ax.add_patch(rect)
            for (inv, pv_name, ts) in proxy_down_cells:
                if inv != inv_id or ts not in ts_index:
                    continue
                ci = ts_index.index(ts)
                pv_label = f"{pv_name} Power(kW)"
                if pv_label not in pivot_plot.index:
                    continue
                ri = list(pivot_plot.index).index(pv_label)
                rect = Rectangle((ci, ri), 1, 1,
                                 facecolor="none", edgecolor="red", linewidth=1.5,
                                 zorder=6)
                ax.add_patch(rect)
        except Exception as e:
            print(f"[viz] availability overlay skipped: {e}")
```

- [ ] **Step 4: Modify `plot_all_inverters` signature + forward overlay**

Find `plot_all_inverters` signature. Replace:

```python
def plot_all_inverters(
    df_plot: pd.DataFrame,
    cell_size: float = CELL_SIZE_DEFAULT,
    empty_pv_map: Optional[Dict[str, List[int]]] = None,
    pv_max_allowed: int = PV_MAX_ALLOWED_DEFAULT,
    max_to_plot: Optional[int] = None,
    pause_seconds: float = PAUSE_SECONDS_DEFAULT,
    close_after_show: bool = False,
) -> Tuple[int, List[Tuple[str, str]]]:
```

With:

```python
def plot_all_inverters(
    df_plot: pd.DataFrame,
    cell_size: float = CELL_SIZE_DEFAULT,
    empty_pv_map: Optional[Dict[str, List[int]]] = None,
    pv_max_allowed: int = PV_MAX_ALLOWED_DEFAULT,
    max_to_plot: Optional[int] = None,
    pause_seconds: float = PAUSE_SECONDS_DEFAULT,
    close_after_show: bool = False,
    availability_overlay: Optional[Dict[str, object]] = None,
) -> Tuple[int, List[Tuple[str, str]]]:
```

Then in the inner call, replace:

```python
            plot_single_inv_heatmap(
                inv_id=inv,
                df=df_plot,
                pv_max_allowed=pv_max_allowed,
                cell_size=cell_size,
                show=True,
                close_after_show=close_after_show,
                empty_pv_map=empty_pv_map,
            )
```

With:

```python
            plot_single_inv_heatmap(
                inv_id=inv,
                df=df_plot,
                pv_max_allowed=pv_max_allowed,
                cell_size=cell_size,
                show=True,
                close_after_show=close_after_show,
                empty_pv_map=empty_pv_map,
                availability_overlay=availability_overlay,
            )
```

- [ ] **Step 5: Run, verify pass**

Run:
```
py -c "from pv_pipeline.viz import plot_single_inv_heatmap, plot_all_inverters; import inspect; assert 'availability_overlay' in inspect.signature(plot_single_inv_heatmap).parameters; assert 'availability_overlay' in inspect.signature(plot_all_inverters).parameters; print('OK')"
```
Expected: `OK`.

- [ ] **Step 6: Commit**

```
git add pv_pipeline/viz.py
git commit -m "feat(m2e): add optional availability_overlay parameter (default off -> parity with v1.3)"
```

---

## Task 15: Notebook v1.4 — copy v1.3 + add Cell 4 (M2e run)

**Files:**
- Create: `20260507stringmap_v1.4.ipynb`

- [ ] **Step 1: Copy v1.3 to v1.4**

Run:
```
py -c "import shutil; shutil.copy('20260507stringmap_v1.3.ipynb', '20260507stringmap_v1.4.ipynb'); print('OK')"
```
Expected: `OK`.

- [ ] **Step 2: Insert new Cell 4 (M2e run) before existing CSV-save cell**

Save the script below as `_insert_m2e_cell.py` (temp file in repo root) and execute via `py _insert_m2e_cell.py`:

```python
import json

NB_PATH = "20260507stringmap_v1.4.ipynb"

new_cell_src = '''# Cell 4 — M2e Hybrid Availability (Phase 1)
import os
from pv_pipeline.m2_config import load_m2_config
from pv_pipeline.core import M2Engine
from pv_pipeline.availability import M2eAvailability
import pandas as pd

M2_CFG_PATH = os.path.join(REPO_DIR, 'config', 'm2_config.yaml')
cfg = load_m2_config(M2_CFG_PATH)

required = ['Inverter_ID', 'Start Time', 'Inverter status']
missing = [c for c in required if c not in combined_df.columns]
if missing:
    print(f'[M2e] skipped: missing columns {missing}')
else:
    engine = M2Engine([M2eAvailability()])
    findings = engine.run_all(combined_df, cfg)

    st_dates = sorted(pd.to_datetime(combined_df['Start Time'], errors='coerce').dropna().dt.date.unique())
    if len(st_dates) == 0:
        datestr = 'unknown'
    elif len(st_dates) == 1:
        datestr = st_dates[0].strftime('%Y%m%d')
    else:
        datestr = f"{st_dates[0].strftime('%Y%m%d')}-{st_dates[-1].strftime('%Y%m%d')}"

    out_dir = os.path.join(REPO_DIR, cfg['m2e'].get('output_dir', 'outputs'))
    os.makedirs(out_dir, exist_ok=True)

    jsonl_path = os.path.join(out_dir, f'findings_{datestr}.jsonl')
    M2Engine.write_jsonl(findings, jsonl_path)

    summary_df = M2Engine.to_summary_df(findings)
    csv_path = os.path.join(out_dir, f'availability_{datestr}.csv')
    if summary_df.empty:
        pd.DataFrame(columns=['inverter_id','sub_module','severity','value','threshold','message']).to_csv(csv_path, index=False, encoding='utf-8')
    else:
        summary_df.to_csv(csv_path, index=False, encoding='utf-8')

    print(f'[M2e] findings written: {jsonl_path} ({len(findings)} records)')
    print(f'[M2e] summary written : {csv_path}')

    if not summary_df.empty:
        print('\\nSeverity distribution:')
        print(summary_df['severity'].value_counts().to_string())
        worst = summary_df[summary_df['sub_module']=='M2e_inverter'].sort_values('value').head(10)
        if not worst.empty:
            print('\\nTop-10 worst inverters (uptime%):')
            print(worst[['inverter_id','value','severity']].to_string(index=False))
'''

with open(NB_PATH, "r", encoding="utf-8") as f:
    nb = json.load(f)

new_cell = {
    "cell_type": "code",
    "metadata": {},
    "execution_count": None,
    "outputs": [],
    "source": new_cell_src.splitlines(keepends=True),
}

csv_idx = None
for i, c in enumerate(nb["cells"]):
    if c.get("cell_type") == "code":
        src = "".join(c.get("source", []))
        if "google.colab" in src and "df_plot.to_csv" in src:
            csv_idx = i
            break

if csv_idx is None:
    nb["cells"].append(new_cell)
else:
    nb["cells"].insert(csv_idx, new_cell)

with open(NB_PATH, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print("OK", len(nb["cells"]), "cells; m2e inserted at idx", csv_idx if csv_idx is not None else len(nb["cells"]) - 1)
```

Run: `py _insert_m2e_cell.py`
Expected: `OK 5 cells; m2e inserted at idx 3` (or similar index).

Cleanup: `py -c "import os; os.remove('_insert_m2e_cell.py'); print('removed')"`

- [ ] **Step 3: Verify notebook is valid JSON with 5 cells**

Run:
```
py -c "import json; nb=json.load(open('20260507stringmap_v1.4.ipynb','r',encoding='utf-8')); print('cells:', len(nb['cells'])); print('types:', [c['cell_type'] for c in nb['cells']])"
```
Expected: `cells: 5` and types include code + markdown mix.

- [ ] **Step 4: Commit**

```
git add 20260507stringmap_v1.4.ipynb
git commit -m "feat(m2e): add notebook v1.4 with Cell 4 M2e Hybrid Availability"
```

---

## Task 16: Integration test — run pipeline against real data

**Files:** read-only against `example raw data/20260507/`; writes to `outputs/`.

**Goal**: confirm end-to-end pipeline produces valid artefacts.

- [ ] **Step 1: Run cells 1-4 inline via py launcher**

Save script below as `_integration_check.py` and run `py _integration_check.py`:

```python
import os
import sys

REPO_DIR = os.getcwd()
sys.path.insert(0, REPO_DIR)

FOLDER = os.path.join(REPO_DIR, "example raw data", "20260507")
EXPECTED_FILES = ["1-2.xlsx", "3-10.xlsx"]

from pv_pipeline.data_loader import find_expected_files, load_and_prepare_data
FILE_PATHS = find_expected_files(FOLDER, EXPECTED_FILES)
print("Files:", FILE_PATHS)

from pv_pipeline.transformations import (
    add_inverter_id, add_pv_power_columns, add_total_pv_power
)
combined_df = load_and_prepare_data(
    folder_path=FOLDER, expected_files=EXPECTED_FILES,
    excel_header_row=3, usecols=None, nrows=None,
)
combined_df = add_inverter_id(combined_df)
combined_df, pv_cols = add_pv_power_columns(combined_df)
combined_df = add_total_pv_power(combined_df, pv_cols)
print("combined_df:", combined_df.shape, "invs:", combined_df["Inverter_ID"].nunique())

from pv_pipeline.m2_config import load_m2_config
from pv_pipeline.core import M2Engine
from pv_pipeline.availability import M2eAvailability
import pandas as pd

cfg = load_m2_config(os.path.join(REPO_DIR, "config", "m2_config.yaml"))
engine = M2Engine([M2eAvailability()])
findings = engine.run_all(combined_df, cfg)

st_dates = sorted(pd.to_datetime(combined_df["Start Time"], errors="coerce").dropna().dt.date.unique())
if len(st_dates) == 1:
    datestr = st_dates[0].strftime("%Y%m%d")
else:
    datestr = f"{st_dates[0]:%Y%m%d}-{st_dates[-1]:%Y%m%d}"

out_dir = os.path.join(REPO_DIR, "outputs")
os.makedirs(out_dir, exist_ok=True)
jsonl_path = os.path.join(out_dir, f"findings_{datestr}.jsonl")
M2Engine.write_jsonl(findings, jsonl_path)

summary_df = M2Engine.to_summary_df(findings)
csv_path = os.path.join(out_dir, f"availability_{datestr}.csv")
if summary_df.empty:
    pd.DataFrame(
        columns=["inverter_id","sub_module","severity","value","threshold","message"]
    ).to_csv(csv_path, index=False, encoding="utf-8")
else:
    summary_df.to_csv(csv_path, index=False, encoding="utf-8")

print("findings:", len(findings))
print("jsonl:", jsonl_path, "size=", os.path.getsize(jsonl_path))
print("csv:", csv_path, "size=", os.path.getsize(csv_path))
if not summary_df.empty:
    print("severity:")
    print(summary_df["severity"].value_counts().to_string())
    print("sub_module:")
    print(summary_df["sub_module"].value_counts().to_string())
```

Run: `py _integration_check.py`

Expected output:
- `combined_df: (28836, ...)` and `invs: 193`.
- `[M2e] shutdown_time mode = EVENT`.
- (Optional) `[M2e] UNKNOWN status values` warning if any unknowns; with default mapping over the 7 known statuses, expected 0 unknowns.
- `findings: <N>` (some integer ≥ 0).
- `jsonl` size > 0 (or 0 if no findings; csv still exists with header).

Cleanup: `py -c "import os; os.remove('_integration_check.py'); print('removed')"`

- [ ] **Step 2: Verify output artefacts**

Run:
```
py -c "import pandas as pd, json, os; cands=[f for f in os.listdir('outputs') if f.startswith('availability_')]; print('csv files:', cands); df=pd.read_csv(os.path.join('outputs', cands[0])); print('csv rows:', len(df)); jsonls=[f for f in os.listdir('outputs') if f.startswith('findings_')]; lines=open(os.path.join('outputs', jsonls[0]),'r',encoding='utf-8').readlines(); print('jsonl lines:', len(lines)); print('first parse keys:', list(json.loads(lines[0]).keys()) if lines else None)"
```
Expected: `csv rows == jsonl lines`. Keys: `timestamp, inverter_id, pv_string, sub_module, severity, value, threshold, message, extra`.

- [ ] **Step 3: Sanity-check severity & value range**

Run:
```
py -c "import pandas as pd, os; cands=[f for f in os.listdir('outputs') if f.startswith('availability_')]; df=pd.read_csv(os.path.join('outputs', cands[0])); print(df.groupby(['sub_module','severity']).size().to_string() if not df.empty else 'no findings'); print('value range:', df['value'].min() if not df.empty else None, df['value'].max() if not df.empty else None)"
```
Expected: severity distributed (not all one severity) when findings exist; `value` (uptime_pct) ∈ [0, 100].

- [ ] **Step 4: Decide whether outputs/ should be committed**

Default: do **not** commit `outputs/*.csv` and `outputs/*.jsonl` (local artefacts). Only `outputs/.gitkeep` is committed.

If any code tweak was needed during this integration step, commit it separately:
```
git status
# If code modified during debugging:
# git add <files>
# git commit -m "fix(m2e): <describe>"
```

---

## Task 17: Manual notebook smoke test — run v1.4 in Jupyter or Colab

**Files:** none modified.

- [ ] **Step 1: Open `20260507stringmap_v1.4.ipynb` in Jupyter or Colab**

Local: `py -m jupyter notebook 20260507stringmap_v1.4.ipynb` (atau Colab: upload + mount Drive). Pastikan working directory adalah folder repo (mengandung `pv_pipeline/`).

- [ ] **Step 2: Run cells in order: 1 → 2 → 3 → 4 → 5**

Expected:
- Cell 1: gdrive download finishes, prints `FILE_PATHS`.
- Cell 2: prints `combined_df rows: 28836 columns: 117`, `Found 193 unique Inverter_IDs.`, pivot shape.
- Cell 3: heatmap loop renders (output identik v1.3 — overlay tidak aktif default).
- Cell 4: prints `[M2e] shutdown_time mode = EVENT`, written paths, severity distribution table, top-10 worst inverters.
- Cell 5: di Colab → trigger CSV download. Lokal → `ModuleNotFoundError: google.colab` (acceptable, sesuai parity v1.3).

- [ ] **Step 3 (optional): Toggle overlay flag**

Edit `config/m2_config.yaml`: set `show_overlay: true`. Re-run Cell 1-4 to populate `findings`. Untuk Phase 1 minimal, Cell 3 di v1.4 belum membaca `show_overlay` secara otomatis — overlay wiring di Cell 3 ditangguhkan ke iterasi berikutnya. Jika ingin test overlay sekarang, jalankan manual:

```python
# Di sel temporary setelah Cell 4
from pv_pipeline.viz import plot_all_inverters
inv_status_per_ts = {
    (str(r["Inverter_ID"]), r["Start Time"]): r["_status_class"]
    for _, r in df_plot.merge(
        combined_df[["Inverter_ID","Start Time"]].assign(
            _status_class=combined_df["Inverter status"].apply(
                lambda s: __import__("pv_pipeline.availability", fromlist=["_classify_status"])._classify_status(
                    s, cfg["m2e"]["inverter_status_map"]
                )
            )
        ),
        on=["Inverter_ID","Start Time"], how="left"
    ).iterrows()
}
proxy_down_cells = {
    (f.inverter_id, f.pv_string, pd.to_datetime(f.timestamp))
    for f in findings if f.sub_module == "M2e_string_proxy"
}
plot_all_inverters(df_plot, empty_pv_map=EMPTY_PV_MAP_CLEAN,
                   max_to_plot=3,
                   availability_overlay={
                       "inv_status_per_ts": inv_status_per_ts,
                       "proxy_down_cells": proxy_down_cells,
                   })
```

- [ ] **Step 4: Mark task done (no commit)**

Visual verification only. If overlay toggling reveals issues, file follow-up tasks.

---

## Self-review checklist (after writing this plan)

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| §4 architecture / file map | Tasks 1, 13 |
| §5 plugin interface (Severity, M2Finding, SubModule, M2Engine) | Tasks 2, 3, 4 |
| §6.1 input contract / required cols | Task 12 (`run()` checks missing cols) |
| §6.2 Step 1 status mapping | Task 7 |
| §6.2 Step 2 auto-detect mode | Task 8 |
| §6.2 Step 3 inverter-level + severity | Tasks 9, 10 |
| §6.2 Step 4 string proxy + debounce | Task 11 |
| §6.3 output writers (CSV + JSONL) | Task 4 (M2Engine) + Task 15 (notebook Cell 4) |
| §7 config YAML | Tasks 5, 6 |
| §8 notebook v1.4 cells | Task 15 |
| §9 backward compatibility | Tasks 5 (defaults), 12 (missing-col guard), 14 (overlay default off) |
| §10 test plan synthetic | Tasks 7, 8, 9, 10, 11, 12 (smoke tests) |
| §10 test plan integration | Task 16 |
| §13 risks documented | Task 8 (auto-detect for risk #4); rest documented in spec |

All spec requirements covered.

**2. Placeholder scan:** No "TBD", "TODO", or "implement later" in any task. All steps have explicit code, commands, and expected outputs.

**3. Type / name consistency:**
- `Severity`, `M2Finding`, `SubModule`, `M2Engine` — defined Tasks 2-4, used Tasks 9, 10, 11, 12, 15.
- `_classify_status(status, keymap) -> str` — Task 7 → Task 12.
- `_detect_shutdown_time_mode(sd, st, force) -> Tuple[str, Series, Series]` — Task 8 → Task 12.
- `_severity_for_uptime(pct, th) -> Tuple[Severity, float]` — Task 9 → Tasks 10, 11.
- `_compute_inverter_availability(df, mode, cfg, interval_minutes, sd_parsed=None, st_parsed=None) -> list` — Task 10 → Task 12.
- `_compute_string_proxy(df, pv_cols, cfg, interval_minutes) -> list` — Task 11 → Task 12.
- `_detect_pv_power_cols`, `_estimate_interval_minutes` — defined Task 12, used Task 12.
- `M2eAvailability(SubModule).run(combined_df, config) -> list[M2Finding]` — Task 12, called Task 15.

All names consistent across tasks.
