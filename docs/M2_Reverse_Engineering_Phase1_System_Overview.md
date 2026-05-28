# M2 PV Performance — Reverse Engineering Phase 1: System Overview

**Fokus**: Notebook `20260514stringmap_v1.5.ipynb` + paket `pv_pipeline/` versi 0.20.0
**Site**: PLTS-IKN (lat −0.9912, lon 116.6381), 10 Wiring Box (WB01-WB10), 193 inverter Huawei, panel Jinko JKM625N (bifacial dual-glass)
**Tanggal review**: 2026-05-28
**Status verifikasi**: ✅ Master Context dibaca penuh · ✅ Notebook dipetakan cell-by-cell · ✅ Modul `pv_pipeline/` di-survey · ✅ Config files dibaca

---

## 0. Cara Membaca Dokumen Ini

Dokumen ini adalah **peta jalan tingkat sistem**. Penjelasan rumus matematis penuh per detector (Bagian 2 di permintaan Anda) dan desain Excel per detector (Bagian 3) akan keluar dalam **iterasi berikutnya** — satu detector per iterasi, agar setiap rumus diverifikasi langsung terhadap kode dan tidak disederhanakan demi muat satu dokumen.

Setiap nama file di dokumen ini relatif terhadap repo root `C:\Users\nabil\Downloads\SolarYieldPro-main\kodingan pv string`.

---

## 1. Konteks dan Tujuan Sistem

Notebook ini bukan sekadar "heatmap PV string". Sejak v1.2 → v1.5 (yaitu sepanjang Mei 2026), notebook telah berkembang menjadi **frontend dari sebuah pipeline analitik PLTS bernama M2 Engine** yang berisi 8 detector aktif. Cell-cell di notebook (Cell 4 khususnya) hanya melakukan orchestration; semua logika perhitungan berada di paket Python `pv_pipeline/` (~13.000 baris, 27 modul).

Tujuan utama M2 adalah **diagnosis diferensial underperformance per PV string**: membedakan soiling, shading, kerusakan kabel DC, intermittent fault, ground fault, dan ketidaktersediaan (availability loss), dengan baseline berbasis fisika (pvlib) — bukan sekadar mean statistik.

Master Context (`M2_PV_Performance_Master_Context.docx`) mendefinisikan **target idealnya** dalam 6 modul: M2a (Soiling/Shading), M2b (DC Cable Fault), M2c (Microcrack EL+IV), M2d (Bifacial Backside), M2e (Availability), M2f (Loss Attribution). Yang sudah live di notebook v1.5 adalah M2a (3 dari 3 sub-detector), M2b (3 dari 4 sub-detector — LSTM-AE skeleton, belum terlatih), M2e (1 dari 1), plus M2 IsolationForest sebagai general anomaly detector. M2c, M2d, dan M2f **belum diimplementasi** (butuh sensor EL/IV, rear POA, dan SHAP-based attribution).

---

## 2. Arsitektur Notebook End-to-End

Notebook v1.5 terdiri dari 9 cell (1 markdown + 8 code). Berikut peran masing-masing:

| Cell | Tipe | Baris | Peran |
|---|---|---|---|
| 0 | Markdown | 48 | Header notebook + changelog |
| 1 | Code | 54 | Resolve repo root, download Excel inverter dari Google Drive via `gdown` |
| 2 | Code | 27 | Load Excel → `combined_df`. Hitung `PVx Power(kW) = V × I / 1000`, pivot per-inverter |
| 3 | Code | 22 | Heatmap matplotlib per inverter (PV1..PV28 × waktu) |
| **4** | Code | **248** | **M2 Pipeline UNIFIED** — instantiate 8 detector + run + write JSONL/XLSX multi-sheet. Inti analitis. |
| 5 | Code | 161 | Performance Ratio harian (Wave 7) + cross-check Curtailment (Wave 11) |
| 6 | Code | 350 | Sanity check infrastruktur Sprint 3.1/3.2: POAProvider, AlbedoLoader, CellTempProvider, PanelSpec |
| 7 | Code | 166 | Baseline Accumulator: simpan data NORMAL ke `baseline/{YYYY-MM}/{YYYY-MM-DD}.parquet` untuk training LSTM-AE |
| 8 | Code | 37 | Simpan `df_plot` ke CSV via `google.colab.files.download` (legacy Colab path) |

### Aliran Data (Dependency)

```
                       ┌─────────────────────────────┐
                       │ Google Drive (xlsx inverter) │
                       └──────────────┬──────────────┘
                                      │  gdown
                                      ▼
  ┌────────────┐  Cell 1: resolve REPO_DIR + download xlsx
  │  Cell 1    │
  └─────┬──────┘
        │
        ▼  Cell 2: load_and_prepare_data → combined_df (~28.8k baris × ~117 kol × 193 inverter)
  ┌────────────┐         Tambah Inverter_ID, PVx Power(kW) = V×I/1000, Total_PV_power_kW, pivot
  │  Cell 2    │
  └─────┬──────┘
        │
        ├──────────────┬──────────────────────────────────────────┐
        ▼              ▼                                          ▼
  ┌──────────┐  ┌──────────┐                              ┌──────────┐
  │ Cell 3   │  │ Cell 4   │  ← inti analitis             │ Cell 8   │  ← legacy CSV
  │ heatmap  │  │ M2 8-det │                              │ download │
  └──────────┘  └─────┬────┘
                      │ menghasilkan: cfg, findings, sm_e,
                      │              poa_provider, panel_spec, cell_temp_provider,
                      │              DATA_DATESTR, outputs/m2_findings_<date>.xlsx
                      │
                      ├──────────────┬──────────────┐
                      ▼              ▼              ▼
                ┌──────────┐  ┌──────────┐  ┌──────────┐
                │ Cell 5   │  │ Cell 6   │  │ Cell 7   │
                │ PR + cur-│  │ Sanity   │  │ Baseline │
                │ tailment │  │ POA/Pan- │  │ Accum.   │
                │ Wave 7   │  │ el/Tcell │  │ NORMAL → │
                │ + 11     │  │          │  │ parquet  │
                └──────────┘  └──────────┘  └────┬─────┘
                                                 │
                                                 ▼
                                         baseline/YYYY-MM/YYYY-MM-DD.parquet
                                         (untuk training LSTM-AE Sprint 4 — BLOCKED)
```

**Catatan dependency yang penting**:
- Cell 5, 6, 7 semua bergantung pada `combined_df` (dari Cell 2), `cfg` (dari Cell 4), `DATA_DATESTR` (dari Cell 4), dan `poa_provider` (dari Cell 4). Jadi Cell 4 adalah **kunci**: tanpa Cell 4, Cell 5/6/7 raise `RuntimeError`.
- Cell 3 dan Cell 8 berdiri sendiri di jalur visualisasi-CSV legacy — tidak berinteraksi dengan M2 engine.
- Cell 7 secara opsional membaca `findings` dari Cell 4 untuk auto-skip inverter-day yang punya finding CRITICAL/HIGH (logic di `baseline.py::BaselineAccumulator.filter_combined_df`).

---

## 3. Arsitektur Paket `pv_pipeline/`

### 3.1 Core Plugin Framework (`pv_pipeline/core.py`)

Berisi 4 entitas utama yang digunakan semua detector:

- **`Severity`** (Enum, 5 level): `NORMAL`, `INFO`, `MEDIUM`, `HIGH`, `CRITICAL`. Berperan sebagai output severity dari setiap finding.
- **`M2Finding`** (frozen dataclass): satuan output detector. 12 field — `timestamp`, `inverter_id`, `pv_string`, `sub_module`, `severity`, `value`, `threshold`, `message`, `extra`, `fault_type`, `confidence` (0-100), `evidence` (dict). Field `confidence` dan `evidence` baru ditambahkan di Sprint 1+2 untuk M2b.
- **`SubModule`** (base class): semua detector mewarisi ini. Method utama `run(combined_df, config) → List[M2Finding]`. Multi-sheet output melalui `self.artifacts: Dict[str, pd.DataFrame]` — setiap key jadi 1 sheet xlsx.
- **`M2Engine`** (orchestrator): `run_all(combined_df, cfg)` jalankan semua submodule + concatenate findings. Static methods `write_jsonl()`, `write_xlsx_multi(findings, submodules, path)` menulis output ke disk.

Pola plugin-based ini memenuhi spec Master Context Section 6.1 (PlantConfig / SubModule / M2Engine). PlantConfig dan StringConfig saat ini **implicit** — tersebar di `config/site_geometry.yaml`, `config/panel_spec.yaml`, dan `config/strings.yaml`, belum di-encapsulate dalam dataclass.

### 3.2 Inventory Modul

```
pv_pipeline/
├── core.py                  Severity, M2Finding, SubModule, M2Engine, load_empty_pv_map
├── m2_config.py             DEFAULT_M2_CONFIG + load_m2_config(yaml_path) → deep-merge user override
├── data_loader.py           gdown wrapper + safe_read_excel + load_and_prepare_data
├── transformations.py       add_inverter_id (Inv_A_2XX_IKN → WB02-INVxx), add_pv_power_columns, pivot
├── string_config.py         load_empty_pv_map dari strings.yaml
├── viz.py                   Cell 3 heatmap (matplotlib)
├── preprocessing.py         Hampel outlier filter (pvanalytics) — Wave 9 A/B
├── physics.py               Pmax, P_expected, Kt, ΔP, energy integration, PR (IEC 61724-1)
├── panel_spec.py            PanelSpec dari panel_spec.yaml; Voc helpers (per Tcell)
├── voc_estimator.py         Voc_actual @ I→0 (median V saat I < threshold)
├── cell_temp.py             CellTempProvider: per-WS measurement + SAPM fallback
├── baseline.py              BaselineAccumulator: filter NORMAL → daily parquet
├── availability.py          [M2eAvailability] hybrid inverter+string availability
├── peer_zscore.py           [M2bPeerZScore] Rstr=V/I peer Z-score + voc_ratio rule
├── open_circuit.py          [M2bOpenCircuit] I/I_q95 < 5% + debounce
├── ground_fault.py          [M2bGroundFault] V_to_ground triple-signal
├── iforest.py               [M2IForest] sklearn IsolationForest per inverter, 5-feat
├── m2a/
│   ├── shading.py           [M2aShading] Diurnal CV + PR-proxy + AM/PM asymmetry
│   ├── soiling.py           [M2aSoiling] rdtools SRR (SKELETON — gracefully insufficient_data)
│   └── low_irradiance.py    [M2aLowIrradiance] OLS regression PR_proxy vs POA di 50-250 W/m²
├── poa/
│   ├── loader.py            PyranometerLoader (multi-year xlsx)
│   ├── pvlib_estimator.py   3 clear-sky model (ineichen/simplified_solis/haurwitz) + Perez transposition
│   ├── albedo_loader.py     NSRDB TMY 30-min
│   └── provider.py          POAProvider orchestrator + auto fallback chain
├── weather/
│   └── loader.py            AmbientTempLoader, WindSpeedLoader, WindDirectionLoader
├── generation/
│   └── loader.py            GenerationLoader (IKN Generation Summary PV daily kWh)
├── training_data.py         BaselineLoader + SequenceBuilder (96-step @ 15-min) — Sprint 4 skeleton
├── lstm_ae.py               LSTM-AE PyTorch + M2bIntermittentDetector — Sprint 4 skeleton (BLOCKED)
└── dashboard/               Streamlit prototype (Fase 4) — masih in-development
```

### 3.3 Stack Library Eksternal Aktif

Berdasarkan `requirements.txt` + import statements:
- **Solar physics**: `pvlib`, `pvanalytics`, `rdtools` (skeleton soiling)
- **ML / numerik**: `numpy`, `pandas`, `scikit-learn` (IsolationForest), `pyarrow` (parquet), `pytorch` (LSTM-AE skeleton, belum dilatih)
- **I/O**: `openpyxl`, `gdown`, `PyYAML`
- **Visualisasi**: `matplotlib`; Streamlit untuk dashboard (Fase 4)
- **Testing**: `pytest` (418 test passing per snapshot terakhir di Master Context)

---

## 4. Inventory Detector — Status Aktif (Cell 4)

Berdasarkan inspeksi langsung Cell 4 notebook v1.5 dan `m2_config.yaml`:

| # | Detector | Modul | Status | Default Enabled | fault_type | Tampil di Sheet "Findings"? |
|---|---|---|---|---|---|---|
| 1 | M2eAvailability | `availability.py` | ✅ produksi | ON | (none, severity-based) | ✅ |
| 2 | M2bPeerZScore | `peer_zscore.py` | ✅ produksi | ON | `high_R` | ✅ |
| 3 | M2bOpenCircuit | `open_circuit.py` | ✅ produksi | ON | `open_circuit` | ✅ |
| 4 | M2bGroundFault | `ground_fault.py` | ✅ produksi | ON | `ground_fault` | ✅ |
| 5 | M2IForest | `iforest.py` | ⚠ noisy | OFF (opt-in via yaml) | `anomaly` | ❌ excluded |
| 6 | M2aShading | `m2a/shading.py` | ✅ opt-in | OFF default, ON di yaml saat ini | `shading_morning/afternoon/uniform` | ❌ excluded |
| 7 | M2aLowIrradiance | `m2a/low_irradiance.py` | ✅ opt-in | OFF default, ON di yaml saat ini | `low_irradiance_underperform / general_underperform` | ✅ |
| 8 | M2aSoiling | `m2a/soiling.py` | 🟡 SKELETON | OFF | `insufficient_data` sampai 90+ hari baseline | ❌ |

**Catatan tentang `exclude_from_findings_sheet=true`**: 4 detector (iforest, shading, soiling, low_irradiance saat dieksklusi) menulis ke sheet artefak masing-masing (`M2_iforest_AnomalyScores`, dst.), namun **tidak masuk sheet Findings utama** dan tidak men-trigger auto-skip baseline di Cell 7. Alasan: iforest dengan `contamination=0.01` bisa emit ribuan finding per hari → membanjiri Findings sheet dan membuang data baseline yang sebenarnya valid. Detector M2b yang lebih konservatif tetap masuk Findings.

**Detector yang BELUM ada di sistem real** (vs spec Master Context):
- M2b LSTM-AE Intermittent (`lstm_ae.py::M2bIntermittentDetector`) — skeleton ada, `enabled=False`, **BLOCKED** sampai ≥3 bulan data baseline (Sprint 4 prerequisite).
- M2c Microcrack (EL Image YOLOv8 + IV Curve) — belum ada modul, butuh kampanye EL imaging + IV tracer.
- M2d Bifacial Backside — belum ada modul, butuh rear POA sensor (min 4 per row per IEC TS 60904-1-2).
- M2f Loss Attribution + Pareto + SHAP — belum ada modul.

---

## 5. Output Sheet xlsx (`outputs/m2_findings_<datestr>.xlsx`)

Sheet yang di-emit Cell 4 (multi-sheet via `M2Engine.write_xlsx_multi`):

```
m2_findings_<datestr>.xlsx
├── Findings                              ← gabungan finding non-excluded
├── M2e_hybrid_AllStrings                 ← per-(inverter, PV) uptime% + severity
├── M2e_hybrid_InverterLog                ← per-inverter operation log (startup/shutdown/duration)
├── M2b_peer_zscore_StringStatus          ← per-PV: NORMAL | high_R | EMPTY
├── M2b_peer_zscore_GateFailureSummary    ← diagnostic kalau fan-out triggered
├── M2b_peer_zscore_PreprocessingAudit    ← (kalau preprocessing.enabled=True)
├── M2b_open_circuit_StringStatus         ← per-PV: NORMAL | open_circuit | EMPTY
├── M2b_open_circuit_PreprocessingAudit
├── M2b_ground_fault_StringStatus         ← per-PV: NORMAL | ground_fault | EMPTY
├── M2b_ground_fault_InverterEvents       ← per-inverter, flagged only
├── M2b_ground_fault_PreprocessingAudit
├── M2_iforest_AnomalyScores              ← per-(inv, PV, ts) score
├── M2_iforest_AnomalySummary
├── M2a_shading_HourlyMetrics             ← per-(inv, hour) CV + PR_proxy
├── M2a_shading_ShadingSummary
├── M2a_low_irradiance_LowIrradianceFit   ← regression coef per inverter
├── M2a_low_irradiance_Summary
├── M2a_soiling_EconomicAnalysis          ← payback days
├── M2a_soiling_SoilingRatio              ← rdtools SRR output
└── M2a_soiling_CleaningEvents
```

Output tambahan di luar xlsx: `outputs/m2_findings_<datestr>.jsonl` (1 baris per finding), `outputs/inverter_operation_<datestr>.csv` (legacy M2e log).

---

## 6. Inventory KPI / Metrik (Tabel Ringkas — Detail di Iterasi Berikutnya)

Setiap baris di sini akan diturunkan **rumus matematis penuhnya** di iterasi deep-dive per detector. Untuk sekarang, ini sekadar peta apa-yang-dihitung-di-mana.

### 6.1 KPI Physics-Based Baseline (`physics.py`)

| KPI | Lokasi | Input | Output |
|---|---|---|---|
| **Pmax per module** | `compute_pmax_per_module(poa, tcell, panel_spec)` | POA W/m², Tcell °C, datasheet | W per modul |
| **P_expected per string** | `compute_p_expected_per_string(poa, tcell, panel_spec, wb_id)` | POA, Tcell, wb_id | W per string (scaled × modules_per_string) |
| **Kt (Clearness Index)** | `compute_kt(poa_measured, poa_clearsky)` | POA terukur & POA clear-sky | float 0..>1 |
| **ΔP (Delta Power)** | `compute_delta_power(p_actual, p_expected)` | aktual & expected | (P_act/P_exp) − 1 |
| **Energy integration** | `compute_active_power_integration_kwh(power_kw)` | series kW (5-min) | kWh harian |
| **PR (Performance Ratio)** | `compute_pr(E_act, POA_kwh/m², capacity_kwp)` | E_act, integral POA, capacity | float 0..>1 |

### 6.2 KPI per Detector Aktif

| Detector | KPI utama | Output finding | Severity mapping |
|---|---|---|---|
| **M2eAvailability** | `inverter_uptime_pct`, `string_uptime_pct`, `downtime_min` | per-inverter + per-string | <90 CRITICAL · <95 HIGH · <97 MEDIUM · <99 INFO · ≥99 NORMAL |
| **M2bPeerZScore** | `Rstr = V/I`, `z_score`, `voc_ratio`, `confidence` | per-(inv, PV, source) high_R | `|z|>3.5` HIGH · `|z|>2.5` & voc_ratio>0.95 MEDIUM |
| **M2bOpenCircuit** | `I_ratio = I/I_q95`, `n_debounced_events` | per-(inv, PV) open_circuit | CRITICAL (95% confidence) |
| **M2bGroundFault** | `|V_to_ground|`, `adaptive_z`, `voc_ratio`, `I_z` | per-inverter ground_fault | per `triggered_by`: absolute / adaptive / spec_4.2.3 → 80/70/60% conf |
| **M2IForest** | `anomaly_score` (sklearn), 5-feat (V, I, V_dev, I_dev, R) | per-(inv, PV, ts) | by score quartile |
| **M2aShading** | `CV_h` per jam, `PR_proxy_h`, AM/PM imbalance | per-inverter shading_{morning/afternoon/uniform} | by # suspicious hours |
| **M2aLowIrradiance** | slope_low, slope_mid, R², dari OLS PR vs POA di 50-250 W/m² | per-inverter low_irradiance_underperform vs general_underperform | by slope significance |
| **M2aSoiling** | (saat live) insolation-weighted soiling ratio, cleaning events, payback_days | per-site | rdtools-based |

### 6.3 KPI Sistem (di luar detector)

| KPI | Cell | Sumber |
|---|---|---|
| **Total_PV_power_kW** | Cell 2 | `add_total_pv_power` → `Σ PVx Power(kW)` per timestamp per inverter |
| **PR harian per WB** | Cell 5 | `compute_pr(generation_kwh, POA_kwh, capacity_kwp)` |
| **Curtailment cross-check** | Cell 5 | Bandingkan PR rendah vs kolom Curtailment + Deem Dispatch dari `IKN Generation.xlsx` |
| **POA multi-source comparison** | Cell 6 + Cell 4 (per detector) | 5 source: pyranometer_per_ws, pyranometer_avg, pvlib_clearsky_{ineichen, simplified_solis, haurwitz} |

---

## 7. Konfigurasi Sistem (Single Source of Truth)

Semua threshold dan tunable berada di 5 YAML config (jangan hardcode di kode):

| File | Isi |
|---|---|
| `config/m2_config.yaml` | DEFAULT_M2_CONFIG override: thresholds per detector (m2e, m2b, m2b_open_circuit, m2b_ground_fault, m2a_shading, m2a_soiling, m2a_low_irradiance, m2_iforest), POA source list, preprocessing flag |
| `config/site_geometry.yaml` | Koordinat (lat −0.99, lon 116.64), elev 85m, tz Asia/Makassar, tilt 10°, azimuth 0° (N), `ws_to_wb` mapping (5 WS untuk POA, 4 WS untuk Tcell/Weather), paths ke pyranometer/Tcell/albedo/weather xlsx |
| `config/panel_spec.yaml` | Jinko JKM625N STC + NOCT + temperature coef + bifacial gain + per-WB `modules_per_string` (WB01-02: 24, WB03-10: 26) |
| `config/strings.yaml` | `EMPTY_PV_MAP`: 244 entri inverter → list PV slot yang fisik tidak terpasang (untuk skip dari peer comparison) |
| `config/baseline.yaml` | BaselineAccumulator: skip_scope (`pv_string` default), auto_skip_severity, maintenance_periods (kosong saat ini) |

**Threshold default penting** (untuk verifikasi cepat):
- `m2b.z_threshold = 2.5`, `voc_ratio_threshold = 0.95`
- `m2b_open_circuit.i_ratio_threshold = 0.05`, `poa_threshold_wm2 = 700`, `debounce_consecutive_steps = 20` (≈ 1h40m persistensi pada 5-menitan)
- `m2b_ground_fault.v_to_ground_abs_threshold_v = 50`, `adaptive_z_threshold = 3.0`
- `m2e.string_proxy.pstr_zero_threshold_kw = 0.1`, `sibling_median_active_kw = 1.0`, `debounce = 20`
- `m2a_shading.cv_low_multiplier = 0.5`, `pr_low_multiplier = 0.85`
- `m2a_low_irradiance.poa_low_range = [50, 250]`, `r_squared_min = 0.3`
- `preprocessing.enabled = true`, `window = 15`, `max_deviation = 3.0` (Hampel σ)

---

## 8. Data Input (Raw Files)

Folder `raw data input/` berisi:

| File | Sumber | Resolusi | Periode |
|---|---|---|---|
| `1-2.xlsx`, `3-10.xlsx` | Huawei SmartLogger (193 inverter, 28-36 PV per inverter) | 5 menit | Harian (1 file/hari) |
| `POA PLTS IKN 2025.xlsx`, `2026.xlsx` | Pyranometer 5 WS (WS-1..WS-5) + rata-rata | 5 menit | Multi-tahun |
| `Ambient Temperature PLTS IKN {2025,2026}.xlsx` | 4 WS | 5 menit | 2025-2026 |
| `Wind Speed PLTS IKN {2025,2026}.xlsx` | 4 WS | 5 menit | 2025-2026 |
| `Wind Direction PLTS IKN {2025,2026}.xlsx` | 4 WS (WS-1 sensor missing) | 5 menit | 2025-2026 |
| `PV Module Temperature PLTS IKN.xlsx` | 4 WS × 3 sensor + avg + Overall | 5 menit | 2025-2026 |
| `Surface Albedo Forecast TMY NSRDB PLTS IKN.xlsx` | NSRDB TMY 5-year avg | 30 menit | TMY (bukan aktual) |
| `IKN Generation.xlsx` (sheet "Summary (PV)") | Generation daily kWh per WB + curtailment | Harian | Multi-tahun |
| `Jinko Solar JKM625N 78HL4-BDV datasheet.pdf` | Datasheet panel | — | — |

Kolom Huawei xlsx kritikal: `Inverter_ID`, `Start Time`, `Inverter status`, `Inverter shutdown time`, `Inverter startup time`, `Active power(kW)`, `Internal temperature(℃)` (suhu kabinet inverter — **bukan Tcell modul**), `Voltage between PV– and the ground(V)` (en-dash U+2013), `PV<n> input voltage(V)`, `PV<n> input current(A)` untuk n=1..36 (di-cap PV_MAX_ALLOWED=28).

---

## 9. Findings dari Audit Awal (Sebelum Deep-Dive Detector)

Beberapa hal yang saya verifikasi langsung di kode + worth diketahui sebelum kita masuk ke formula matematis. Dalam semangat skeptis sesuai instruksi Anda:

1. **Cap PV28 vs data PV36** — Notebook men-cap `PV_MAX_ALLOWED = 28` (Cell 1) padahal xlsx Huawei punya PV1..PV36. WB01/WB02 memang punya 18 string aktif (PV1..PV18) sesuai `panel_spec.yaml` (`modules_per_string=24`), sisanya di-mask via `EMPTY_PV_MAP`. **Worth dikonfirmasi**: apakah cap=28 ini hardcoded benar untuk semua WB, atau ada inverter di lapangan yang punya >28 string aktif?

2. **Detector "M2a saat ini enabled di yaml"** — `m2_config.yaml` menyatakan `m2a_shading.enabled: true` dan `m2a_low_irradiance.enabled: true` di file aktual, padahal Master Context dan kode default `enabled=False`. **Konsekuensi**: Cell 4 saat ini akan jalankan shading + low_irradiance detector. Pastikan ini intentional.

3. **`exclude_from_findings_sheet=true` di iforest + shading saat ini** — Berarti finding mereka tidak masuk sheet Findings utama, hanya muncul di artifact sheet masing-masing. Excel design saya nanti akan mereplikasi behavior ini.

4. **`Internal temperature(℃)` ≠ Tcell modul** — Notebook (terutama pre-Wave 6) sempat ambigu. Saat ini Tcell modul datang dari `PV Module Temperature PLTS IKN.xlsx` via `CellTempProvider`, dengan fallback SAPM model. **Jangan gunakan kolom "Internal temperature(℃)"** untuk perhitungan Pmax/voc — itu suhu kabinet inverter.

5. **WS-1 wind direction missing** — Konfigurasi `weather.wind_direction` mencatat data NaN untuk WS-1. Jika kelak ada detector yang pakai wind direction, perlu handle ini.

6. **POA fan-out 5 source** — Setiap detector M2b (peer_zscore, open_circuit, ground_fault) loop di 5 POA source (`emit_all_sources: true`). Artinya finding bisa duplikat dengan `evidence.poa_source` berbeda. Ini *intentional* untuk cross-validation antar source. Excel design perlu reflect ini.

7. **Soiling detector statusnya SKELETON** — `M2aSoiling.run()` cenderung emit finding dengan `fault_type='insufficient_data'` (severity INFO) saat baseline < 90 hari. **Excel saya akan implement versi simplified** (PR drift rolling 14-hari + recovery detection) yang bisa langsung dipakai tanpa menunggu 6 bulan data.

8. **LSTM-AE skeleton** — Modul ada (`lstm_ae.py` + `training_data.py`), tapi model belum dilatih (`enabled=False`). Sampai baseline ≥3 bulan akumulasi, detector ini noop.

---

## 10. Translasi ke Excel — Strategi Umum (Akan Detail per-Detector)

Karena Anda memilih "Include approximate ML detectors", strategi general:

| Tipe perhitungan | Strategi Excel |
|---|---|
| Aritmetika sederhana (PVx Power = V × I / 1000) | Formula langsung |
| Pivot / aggregation per inverter | PivotTable atau formula `SUMIFS/AVERAGEIFS` |
| Median / std / quantile peer | `MEDIAN`, `STDEV.P`, `PERCENTILE.INC` per range sibling |
| Z-score | `(x − MEDIAN) / STDEV.P` |
| Debounce consecutive | Helper column boolean + `COUNTIFS` window OR custom helper (rolling count via array formula) |
| OLS regression (low_irradiance) | `LINEST` (built-in) atau `SLOPE`/`INTERCEPT`/`RSQ` |
| Hampel filter | Sheet helper: rolling median + rolling MAD → boolean outlier mask |
| Isolation Forest | **Approximation**: MAD-based univariate + multi-feature percentile cutoff per inverter. Catat: bukan true iForest. |
| LSTM-AE | **Approximation**: rolling MA residual + std threshold. Sangat lemah vs real LSTM-AE. Akan kita beri caveat eksplisit. |
| rdtools SRR | **Approximation**: PR_daily rolling 14-hari + drift detection + recovery detection. Bukan stochastic Monte Carlo. |
| pvlib clear-sky | Tabel input external (user tempel hasil pvlib) atau approximate Haurwitz: `1098 × cos(zenith) × exp(−0.057/cos(zenith))` |

Excel workbook akan terdiri dari ~15-20 sheet:
- 1 sheet **Config** (semua threshold, mirror m2_config.yaml)
- 1 sheet **Raw_Data** (paste Huawei + meteo)
- 1 sheet **Helpers** (PVx Power, sibling median, masks)
- 1 sheet per detector aktif (8 sheet)
- 1 sheet **Findings_Summary**
- 1 sheet **Dashboard** (chart per WB, distribusi severity, top-10 worst string)

Workbook lengkap akan dibangun **bertahap**, sheet per detector, di iterasi-iterasi berikutnya.

---

## 11. Rekomendasi Urutan Deep-Dive Berikutnya

Berdasarkan kompleksitas, criticality, dan tingkat dependency, saya rekomendasikan urutan ini (Anda bisa override):

| Urutan | Detector | Alasan |
|---|---|---|
| **1** | **M2eAvailability** | Detector tertua, paling matang, ground-truth dari kolom inverter status. Excel-nya straightforward — bisa jadi template untuk yang lain. |
| **2** | **M2bPeerZScore** | Inti spec Master Context 4.2.1. Rumus moderat. Excel-nya butuh sibling median + Z-score per timestamp. |
| **3** | **M2bOpenCircuit** | Logika debounce + I_q95 ratio. Penting untuk fault aktual lapangan (799 CRITICAL persistent per snapshot terakhir). |
| **4** | **M2bGroundFault** | Triple-signal (absolute / adaptive / spec-based confidence). Butuh kolom `Voltage between PV– and the ground(V)`. |
| **5** | **M2aShading** | Diurnal CV + PR_proxy + AM/PM classifier. Excel butuh hourly aggregation. |
| **6** | **M2aLowIrradiance** | OLS regression dual-band — Excel `LINEST` cukup. |
| **7** | **M2IForest** | ML detector. Excel akan jadi approximation MAD-based + caveat eksplisit. |
| **8** | **M2aSoiling** | Skeleton — kita design simplified version (rolling PR drift + recovery). |
| **9** | (opsional) **Physics baseline + PR + Curtailment cross-check** (Cell 5) | Foundation untuk semua detector. |

**Detector LSTM-AE Intermittent** akan kita masukkan sebagai "limitasi" section di Excel (bukan iterasi terpisah) karena memang belum aktif di sistem real.

---

## 12. Yang Akan Datang di Iterasi Berikutnya

Setiap iterasi deep-dive akan menghasilkan:
1. **Markdown technical spec** (`docs/M2_RE_<NN>_<DetectorName>.md`) berisi: rumus matematis penuh dengan notasi LaTeX-style, penjelasan setiap variabel, contoh perhitungan numerik, edge cases yang dihandle kode, perbedaan kode vs spec Master Context.
2. **Sheet baru di workbook Excel** (`docs/M2_PV_Performance_Workbook.xlsx`) — saya akan akumulasi semua detector ke 1 workbook, satu sheet per detector + helper sheet + dashboard.
3. **Section di docx report** — versi compact dari markdown untuk shareability.

**Konfirmasi yang saya butuhkan dari Anda** (untuk iterasi berikutnya):
1. Setuju mulai dari M2eAvailability? Atau Anda mau jump ke detector lain (mis. M2bPeerZScore karena itu inti spec)?
2. Untuk Excel workbook: build 1 file `.xlsx` yang akan di-grow tiap iterasi (rekomendasi), atau 1 file `.xlsx` per detector?
3. Apakah ada detector tertentu yang **prioritas tinggi** untuk Anda (mis. soiling karena cleaning ROI, atau ground_fault karena safety)? Saya bisa pivot urutan.

---

## Sources

Verifikasi langsung di file lokal:
- `M2_PV_Performance_Master_Context.docx` — Section 1-10 + sprint summaries Fase 1 / 1.5 / 2 / 3 / 3 Part 2
- `notebook/20260514stringmap_v1.5.ipynb` — 9 cell, lihat penjelasan Bagian 2
- `pv_pipeline/core.py`, `availability.py`, `peer_zscore.py`, `open_circuit.py`, `ground_fault.py`, `iforest.py`, `m2a/{shading,soiling,low_irradiance}.py`, `physics.py`, `panel_spec.py`, `cell_temp.py`, `baseline.py`, `preprocessing.py`, `lstm_ae.py`, `training_data.py`, `voc_estimator.py`
- `config/{m2_config,site_geometry,panel_spec,baseline}.yaml`
