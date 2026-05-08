# Design Spec — M2e Hybrid Availability + Skeleton Plugin (Fase 1)

**Tanggal:** 2026-05-08
**Status:** Approved (brainstorm), siap untuk implementation plan
**Scope:** Notebook PV string heatmap di `kodingan pv string/`, transisi v1.3 → v1.4
**Master Context refs:** §4.5 M2e String Availability, §5 Roadmap Fase 1

---

## 1. Tujuan

Mengisi gap M2e (String Availability Analysis) di Master Context dengan strategi **hybrid**:

1. **Inverter-level availability** sebagai *baseline* — pakai kolom `Inverter status` + `Inverter shutdown time` + `Inverter startup time` yang sudah ter-load di `combined_df` tapi belum dipakai di v1.3.
2. **String-level proxy availability** — string dianggap "down" bila `Pstr ≈ 0` saat inverter `ON-grid`, mayoritas string sibling aktif, dan ada tanda daylight. *Tanpa pyranometer*, daylight di-proxy oleh "ada inverter lain di plant aktif".
3. Sekaligus **menyiapkan interface plugin minimal** (`M2Finding`, `Severity`, `SubModule`, `M2Engine`) supaya M2b (peer Z-score, Fase 1 berikutnya) dan M2a/c/d/e/f Fase 2+ tinggal plug-in tanpa redesign.

## 2. Non-goals

- **Bukan** physics baseline (pvlib `P_expected`, POA Perez, Tcell SAPM) — itu Fase 2.
- **Bukan** alarm state machine, multi-channel dispatch — itu Fase 4.
- **Bukan** plugin registry / dynamic discovery — `M2Engine` Fase 1 menerima list submodule eksplisit.
- **Bukan** Streamlit dashboard — heatmap notebook tetap dipertahankan.
- **Tidak menyentuh** `data_loader.py`, `transformations.py`, `string_config.py` — Fase 0 work tetap utuh.

## 3. Konteks data

`combined_df` setelah `add_pv_power_columns + add_total_pv_power` punya 117 kolom termasuk:

- **Identifier**: `Inverter_ID` (WB01-INV01..WB02-INV..), `Start Time`, `ManageObject`.
- **Inverter status (M2e source)**: `Inverter status`, `Inverter shutdown time`, `Inverter startup time`.
- **String level**: `PV1 Power(kW)..PV28 Power(kW)` (computed), `Total_PV_power_kW`.
- 193 unique Inverter_ID, 28836 rows untuk 1 hari (interval ~5 menit).

**Hasil inspeksi raw data `example raw data/20260507/{1-2,3-10}.xlsx` (2026-05-08):**

Distinct values `Inverter status` (7 kategori, pola Huawei SmartLogger):

| Status string | Count (1 hari) | Klasifikasi |
|---|---:|---|
| `Grid connected` | 26,397 | **ON** |
| `Grid connected : power limited` | 1,203 | **ON** (curtailed) |
| `Standby : insulation resistance detection` | 539 | TRANSITIONAL |
| `Standby : sunlight detection` | 264 | TRANSITIONAL |
| `Standby : initialization` | 229 | TRANSITIONAL |
| `Standby :  no sunlight` | 199 | TRANSITIONAL |
| `Standby : grid detection` | 5 | TRANSITIONAL |

**Catatan**: tidak ada nilai `Shutdown` / `Fault` di hari sample → inverter-level findings bisa 0 untuk hari ini; sinyal utama datang dari **string-proxy**. Mapping default di §7 disesuaikan agar `"grid connected"` (bukan `"on-grid"`) jadi keyword utama.

`Inverter shutdown time` & `Inverter startup time`: **dtype `str` `"YYYY/MM/DD HH:MM:SS"`** (bukan float), ~98% non-null. Sebagian baris berisi literal `"-"`. Semantik: **timestamp event terakhir** — bila `shutdown_time > startup_time` ⇒ inverter sedang down. Confirms **mode `EVENT`**.

`Start Time` di file sumber: dtype `str` `"YYYY-MM-DD HH:MM:SS"`, di-cast ke datetime di `prepare_df_work` (existing transformations).

## 4. Arsitektur — file & module baru

```
kodingan pv string/
├── 20260507stringmap_v1.4.ipynb         ← notebook baru, v1.3 dipertahankan
├── config/
│   ├── strings.yaml                     ← existing, no change
│   └── m2_config.yaml                   ← BARU: thresholds + status mapping
├── pv_pipeline/
│   ├── (data_loader, transformations, string_config — no change)
│   ├── core.py                          ← BARU: M2Finding, Severity, SubModule, M2Engine
│   ├── availability.py                  ← BARU: M2eAvailability submodule
│   ├── m2_config.py                     ← BARU: load_m2_config(yaml_path) helper
│   └── viz.py                           ← extended: opsional overlay (default OFF)
└── outputs/                             ← BARU folder, dibuat runtime
    ├── availability_YYYYMMDD.csv        ← daily summary (per inverter + per string)
    └── findings_YYYYMMDD.jsonl          ← per-row findings (line-delimited JSON)
```

Alasan terpisah `m2_config.py` (bukan extend `string_config.py`): `string_config` urus `EMPTY_PV_MAP` (data peta string fisik); `m2_config` urus thresholds analitik. Lifecycle berbeda — peta string jarang berubah, threshold sering di-tune.

## 5. Interface plugin (`pv_pipeline/core.py`)

Sengaja minimal (~80 LOC). Tanpa registry, tanpa state machine.

```python
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Optional, Iterable
import json
import pandas as pd

class Severity(str, Enum):
    NORMAL   = "NORMAL"
    INFO     = "INFO"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"

@dataclass(frozen=True)
class M2Finding:
    timestamp: datetime           # kapan terjadi (atau periode start)
    inverter_id: str              # "WB02-INV14"
    pv_string: Optional[str]      # "PV3" ; None bila inverter-level
    sub_module: str               # "M2e_inverter" | "M2e_string_proxy"
    severity: Severity
    value: float                  # nilai yang diukur (mis. uptime_pct)
    threshold: float              # threshold severity yang dilanggar
    message: str                  # human-readable
    extra: dict = field(default_factory=dict)

    def to_jsonl(self) -> str:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        d["severity"] = self.severity.value
        return json.dumps(d, ensure_ascii=False)

class SubModule:
    """Base class. Override `run()` di subclass."""
    name: str = "base"

    def run(self, combined_df: pd.DataFrame, config: dict) -> list[M2Finding]:
        raise NotImplementedError

class M2Engine:
    def __init__(self, submodules: Iterable[SubModule]):
        self.submodules = list(submodules)

    def run_all(self, combined_df: pd.DataFrame, config: dict) -> list[M2Finding]:
        findings: list[M2Finding] = []
        for sm in self.submodules:
            findings.extend(sm.run(combined_df, config))
        return findings

    @staticmethod
    def write_jsonl(findings: list[M2Finding], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for fin in findings:
                f.write(fin.to_jsonl() + "\n")

    @staticmethod
    def to_summary_df(findings: list[M2Finding]) -> pd.DataFrame:
        rows = [
            {**asdict(f), "severity": f.severity.value,
             "timestamp": f.timestamp.isoformat() if f.timestamp else None}
            for f in findings
        ]
        return pd.DataFrame(rows)
```

## 6. Algoritma `M2eAvailability` (`availability.py`)

### 6.1 Input
`combined_df` setelah `add_inverter_id + add_pv_power_columns + add_total_pv_power`. Minimal kolom yang dipakai:
- `Inverter_ID`, `Start Time`, `Inverter status`
- `Inverter shutdown time`, `Inverter startup time` (opsional, fallback bila absent)
- `PV{1..28} Power(kW)`

### 6.2 Pipeline

**Step 1 — Map status → kategori 4-state.**
- Lowercase + substring match terhadap `on_grid_keywords`, `down_keywords`, `transitional_keywords` di config.
- Hasil: kolom `_status_class ∈ {"ON", "DOWN", "TRANSITIONAL", "UNKNOWN"}`.
- Distinct status yang map ke `UNKNOWN` di-print sebagai warning sekali per run dengan count, supaya YAML bisa di-update.

**Step 2 — Auto-detect `shutdown/startup time` dtype.**
- Replace literal sentinel `"-"` dengan NaN dulu (raw data Huawei pakai `-` untuk null).
- Coba `pd.to_datetime(..., format="%Y/%m/%d %H:%M:%S", errors="coerce")`. Jika ≥ 80% non-null → mode `EVENT`.
- Else jika `pd.to_numeric(..., errors="coerce")` ≥ 80% non-null **dan** monotonically non-decreasing per inverter → mode `CUMULATIVE`.
- Else → mode `STATUS_ONLY`.
- Mode terpilih dicetak sekali per run (`[M2e] shutdown_time mode = EVENT`).
- Mode juga bisa di-force lewat config `m2e.shutdown_time_detection: event|cumulative|status_only|auto`.
- Pada raw data 2026-05-07: 98% non-null, format `"YYYY/MM/DD HH:MM:SS"` → auto-detect akan pilih `EVENT`. **`is_down_via_event[row] = (shutdown_time[row] > startup_time[row])`**.

**Step 3 — Inverter-level availability per (inverter, hari).**
- `n_on` = jumlah row `_status_class == "ON"`.
- `n_down` = jumlah row `_status_class == "DOWN"`.
- `n_denominator = n_on + n_down`. TRANSITIONAL & UNKNOWN excluded.
- `uptime_pct = 100 * n_on / n_denominator` (handle `n_denominator == 0` → uptime_pct = NaN, tidak emit finding).
- `downtime_minutes`:
  - mode `EVENT`: hitung dari delta `shutdown_time → startup_time` per event window.
  - mode `CUMULATIVE`: `last - first` cumulative value, convert satuan jika perlu.
  - mode `STATUS_ONLY`: `n_down × interval_minutes` (interval ditebak dari median selisih `Start Time` per inverter, biasanya 5).
- **Severity** dari Master Context §4.5.1:
  - `< critical_below (90)` → CRITICAL
  - `< high_below (95)` → HIGH
  - `< medium_below (97)` → MEDIUM
  - `< info_below (99)` → INFO
  - `≥ 99` → NORMAL (tidak emit finding kecuali `emit_normal: true`)
- Emit **1 `M2Finding` per inverter per hari**, `sub_module="M2e_inverter"`, `pv_string=None`,
  `value=uptime_pct`, `threshold = batas severity yang dilampaui`,
  `extra = {"n_on": ..., "n_down": ..., "downtime_minutes": ..., "mode": ...}`.

**Step 4 — String proxy-down (per inverter, per timestamp, lalu di-aggregate ke event).**

Daylight proxy:
- Untuk tiap timestamp `t`, `is_daylight[t] = (jumlah inverter dengan _status_class == "ON" pada t) ≥ 1`.

Iterasi per row dengan `_status_class == "ON"` dan `is_daylight`:
1. Hitung `sibling_active = [Pstr untuk semua x dalam row ini di mana Pstr > pstr_zero_threshold_kw]`.
2. `sibling_median = median(Pstr untuk semua x di row, ignore NaN)`.
3. **Skip row** bila `sibling_median < sibling_median_active_kw` (default 1.0) — cuaca buruk lokal, tidak fair untuk flag.
4. **Skip row** bila `len(sibling_active) / n_pv_total < min_active_siblings_pct/100` (default 50%).
5. Untuk tiap PV `x` di row qualified ini, jika `Pstr[x] < pstr_zero_threshold_kw` (default 0.1) → catat di buffer `(timestamp, inverter_id, PVx) = candidate_down`.

**Debounce**:
- Untuk tiap (inverter_id, PVx), kelompokkan candidate_down berdasarkan kontigous timestamp (selisih ≤ interval median × 1.5).
- Run length harus ≥ `debounce_consecutive_steps` (default 2) → kualifikasi event.

**Severity per string proxy event**:
- Hitung `string_uptime_pct = 100 - (event_minutes_total / daylight_minutes_for_inverter * 100)` per inverter+string per hari.
- Severity sama threshold-nya dengan inverter-level.
- Emit **1 `M2Finding` per (inverter, PVx) per hari**, `sub_module="M2e_string_proxy"`,
  `value=string_uptime_pct`, `threshold = batas severity`,
  `extra = {"event_minutes": ..., "daylight_minutes": ..., "n_events": ..., "first_event_ts": ..., "last_event_ts": ...}`.

### 6.3 Output writers

Lokasi: `cfg["m2e"]["output_dir"]` (default `"outputs"`, dibuat dengan `os.makedirs(..., exist_ok=True)`).

Filename derivation reuse logic dari Cell 4 v1.3:
- `unique_dates = sorted(combined_df['Start Time'].dropna().dt.date.unique())`
- 1 date → `YYYYMMDD`. Multi-date → `YYYYMMDD-YYYYMMDD` + warning.

Files:
- `outputs/findings_<datestr>.jsonl` — semua `M2Finding` (line-delimited).
- `outputs/availability_<datestr>.csv` — wide table per inverter:
  - Kolom: `Inverter_ID, uptime_pct, downtime_minutes, severity_inverter, n_strings_proxy_down, worst_string, worst_string_uptime_pct, severity_string`.

## 7. Config — `config/m2_config.yaml`

```yaml
m2e:
  inverter_status_map:
    on_grid_keywords:      ["grid connected", "on-grid", "on grid", "ongrid"]
    down_keywords:         ["shutdown", "fault", "stopped", "stop", "error"]
    transitional_keywords: ["standby", "starting", "stopping", "initializing",
                            "initialization", "detecting", "detection",
                            "no sunlight"]
    # Status di luar mapping → UNKNOWN, di-log warning, di-exclude dari denominator.

  shutdown_time_detection: "auto"     # auto | event | cumulative | status_only

  string_proxy:
    pstr_zero_threshold_kw:     0.1
    sibling_median_active_kw:   1.0
    min_active_siblings_pct:    50
    debounce_consecutive_steps: 2

  severity_thresholds:                # uptime_pct < X → severity
    critical_below: 90
    high_below:     95
    medium_below:   97
    info_below:     99
    emit_normal:    false             # ≥99 → NORMAL, default tidak di-emit

  output_dir: "outputs"
  show_overlay:  false                # heatmap overlay (Cell 3)
```

Loader (`pv_pipeline/m2_config.py`):
- `load_m2_config(path) -> dict` — `yaml.safe_load`, return defaults bila file tidak ada (warning).
- Validasi minimal: types & required keys; lainnya forgiving.

## 8. Notebook v1.4

Salin v1.3 ke `20260507stringmap_v1.4.ipynb`. 5 cells:

| Cell | Sumber | Status |
|---|---|---|
| 1 | Config + gdrive download | **Identical** dari v1.3 |
| 2 | Load + transform | **Identical** dari v1.3 |
| 3 | Heatmap per inverter | **+ overlay opsional**: jika `cfg["m2e"]["show_overlay"]`, render shading abu-abu untuk timestamps inverter `_status_class != ON` dan border merah untuk PV cell yang qualified proxy-down. Default `False` → output identik v1.3. |
| 4 | **BARU: M2e** | Code block ~30 LOC: load `m2_config.yaml`, build `M2Engine([M2eAvailability()])`, `run_all`, write JSONL + CSV, print top-10 worst inverters + count findings per severity. |
| 5 | Save df_plot CSV | **Identical** dari v1.3 (tetap `google.colab.files.download`). |

## 9. Backward compatibility & failure modes

- `m2_config.yaml` absent → defaults hardcoded, warning di Cell 4, run continue.
- Kolom `Inverter status` absent di `combined_df` → Cell 4 skip dengan pesan jelas, exit code 0.
- Kolom `Inverter shutdown/startup time` absent → mode auto-fall-back ke `STATUS_ONLY`, warning, jalan.
- Semua thresholds di config; tidak ada magic number di Python.
- v1.3 tidak diubah; v1.2 tidak diubah; user dapat regress kapan pun.

## 10. Test plan

**Synthetic unit tests** (di `if __name__ == "__main__"` di `availability.py`):
1. 1 inverter, 12 row 5-min, semua `On-grid` → uptime 100%, severity NORMAL, 0 findings (karena `emit_normal: false`).
2. 1 inverter, 4 dari 12 row `Shutdown` → uptime 66.7%, severity CRITICAL, 1 finding inverter-level.
3. 2 inverter sibling: A semua ON, B 1 PV stuck di 0 selama 4 row sementara sibling > 5 kW → 1 finding `M2e_string_proxy` untuk B.
4. Status `"Mystery State"` → muncul di warning log "UNKNOWN status: Mystery State (count=N)".
5. `Inverter shutdown time` semua null → mode `STATUS_ONLY`, no exception.

**Integration test (manual, Colab/local dengan data 7 Mei 2026)**:
1. Cell 4 selesai tanpa error.
2. `outputs/findings_20260507.jsonl` valid JSONL, dapat di-`pd.read_json(lines=True)`.
3. `outputs/availability_20260507.csv` punya 193 baris (1 per inverter).
4. Distribusi severity terdistribusi (tidak semuanya satu severity).
5. Top-10 worst inverters logis (manual sanity check terhadap heatmap di Cell 3).

## 11. Estimasi LOC

| File | Approx LOC |
|---|---|
| `pv_pipeline/core.py` | 80 |
| `pv_pipeline/availability.py` | 180 |
| `pv_pipeline/m2_config.py` | 40 |
| `pv_pipeline/viz.py` (extension) | +30 |
| `config/m2_config.yaml` | 25 |
| Notebook Cell 4 baru | 30 |
| **Total** | **~385 LOC** |

## 12. Tidak termasuk Fase 1 (deferred)

- Plugin registry / entry-points discovery.
- AlertManager state machine, NotificationDispatcher.
- POA-based daylight filter (butuh pyranometer data — Fase 2).
- pvlib `P_expected` baseline untuk M2e definisi formal.
- M2b peer Z-score (sibling submodule, Fase 1 task berikutnya — `core.py` interface sudah siap).
- Migrasi dari `google.colab.files` ke local file save (kompat instruksi Phase 0).

## 13. Open issues / risks

1. **Distinct values `Inverter status` belum dikonfirmasi** — mitigasi: warning log + fallback mapping; user dapat update YAML setelah run pertama.
2. **Daylight proxy berisiko false positive** bila plant punya banyak inverter shutdown serentak (mis. grid outage menyeluruh). Mitigasi: severity tetap dihitung per inverter, dan global outage akan tampak sebagai "semua inverter CRITICAL pada hari yang sama" — operator dapat membaca pola ini.
3. **Sibling median threshold 1.0 kW** dipilih ad-hoc; mungkin perlu tuning per plant. Mitigasi: parameter di YAML.
4. **`Inverter shutdown/startup time` semantics belum eksak** — mitigasi: auto-detect + force-mode di config.
