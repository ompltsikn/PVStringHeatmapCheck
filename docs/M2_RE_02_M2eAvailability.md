# M2 Reverse Engineering — Iterasi 2: M2eAvailability

**Modul**: `pv_pipeline/availability.py` (773 baris)
**Class utama**: `M2eAvailability(SubModule)` — `name = "M2e_hybrid"`
**Spec referensi**: Master Context §4.5 String Availability Analysis · §4.5.1 Definisi "Down" per String · `docs/superpowers/specs/2026-05-08-m2e-hybrid-availability-design.md`
**Dipanggil di**: notebook Cell 4, baris instantiate `sm_e = M2eAvailability()`
**Output sheets di xlsx Python**: `M2e_hybrid_AllStrings`, `M2e_hybrid_InverterLog`
**Output Excel workbook**: sheet `Helpers_M2e`, `M2e_Availability`, `M2e_AllStrings`, `Findings_Summary` di `docs/M2_PV_Performance_Workbook.xlsx`
**Status verifikasi**: ✅ Python reference output cocok byte-for-byte dengan Excel computed (5 PV × 12 timestep dummy)

---

## 1. Gambaran Hybrid Availability

Mengapa disebut "hybrid"? Karena modul ini **menjalankan dua pengukuran ketersediaan secara bersamaan** lalu menerbitkan finding masing-masing:

1. **Inverter-level availability** — pakai kolom `Inverter status` dari xlsx Huawei (ground-truth). Memberi tahu apakah seluruh inverter `Grid connected` atau `Shutdown`.
2. **String-level proxy availability** — karena data Huawei tidak punya status per-PV-string, sistem **menebak string yang bermasalah** dengan membandingkan power tiap PV terhadap saudara-saudaranya pada timestamp yang sama.

Master Context §4.5.1 mendefinisikan "down" per string sebagai:

> P_string < 5% dari P_expected_string, saat POA > 50 W/m², selama minimal 2 timestep berturut-turut (debounce noise).

Implementasi `availability.py` berbeda dari spec: alih-alih membandingkan ke `P_expected_string` (yang butuh pvlib + Tcell), modul ini pakai **sibling median** sebagai proxy P_expected (lebih sederhana, tidak butuh meteo data). Trade-off ini didokumentasikan di Master Context: "EMPTY_PV_MAP secara konseptual menjawab Master Context section 4.5.1... Bedanya, di Master Context kondisi down dihitung dinamis (P_string < 5% dari P_expected & POA > 50 W/m² & ≥ 2 timestep), sedangkan notebook men-hardcode string mati." Modul `availability.py` adalah **kompromi pintar** antara hard-code (notebook v1.2) dan full physics-based (spec ideal).

---

## 2. Pipeline `M2eAvailability.run()` — Step by Step

Method `run(combined_df, config)` melakukan urutan 8 langkah berikut. Saya akan turunkan rumus matematis tiap langkah, lalu tunjukkan worked example pada Section 4.

### Langkah 1 — Load `empty_pv_map`

```python
empty_pv_map = get_empty_pv_map(empty_pv_map_path, pv_max_allowed=28)
```

`config/strings.yaml` berisi mapping `Inverter_ID → [pv_indices_kosong]`. Fungsi `get_empty_pv_map` memanggil `load_empty_pv_map` + `sanitize_empty_pv_map`:
- Uppercase semua key (`wb01-inv01` → `WB01-INV01`)
- Convert nilai ke int, drop yang > 28
- Dedup + sort ascending

Total: 244 entri inverter di file aktual (245 baris termasuk header).

### Langkah 2 — Validasi kolom wajib

```python
required = ["Inverter_ID", "Start Time", "Inverter status"]
missing = [c for c in required if c not in combined_df.columns]
if missing:
    warnings.warn(...); return []
```

Jika salah satu hilang, modul return list kosong (no findings). Notebook Cell 4 sudah melakukan precheck juga.

### Langkah 3 — Klasifikasi status inverter (`_classify_status`)

Algoritma: lowercase + substring match dengan **prioritas**:

```
priority(s) = DOWN          if any(kw ∈ down_keywords      where kw.lower() in s.lower())
              ON            elif any(kw ∈ on_grid_keywords where kw.lower() in s.lower())
              TRANSITIONAL  elif any(kw ∈ transitional_keywords where kw.lower() in s.lower())
              UNKNOWN       otherwise
```

Default keyword list (`config/m2_config.yaml` `m2e.inverter_status_map`):

| Kelas | Keywords (substring, case-insensitive) |
|---|---|
| `DOWN` | `shutdown`, `fault`, `stopped`, `stop`, `error` |
| `ON` | `grid connected`, `on-grid`, `on grid`, `ongrid` |
| `TRANSITIONAL` | `standby`, `starting`, `stopping`, `initializing`, `detecting`, `no sunlight`, dll. |

**Insight engineering**: prioritas `DOWN > ON > TRANSITIONAL` penting agar string `"Shutdown: command (was Grid connected)"` di-klasifikasikan DOWN, bukan ON. Status yang tidak match keyword apa pun → `UNKNOWN` + warning dicetak (top 20 unique unknown values).

### Langkah 4 — Deteksi mode shutdown_time (`_detect_shutdown_time_mode`)

Kolom `Inverter shutdown time` dan `Inverter startup time` bisa berisi tiga format berbeda:

| Mode | Kriteria deteksi | Konsekuensi |
|---|---|---|
| **EVENT** | ≥ 80% nilai bisa di-parse `pd.to_datetime()` | Engine pakai delta `shutdown_time − startup_time` sebagai upper bound downtime |
| **CUMULATIVE** | ≥ 80% nilai bisa di-parse `pd.to_numeric()` (mis. jam kumulatif) | Saat ini engine tidak melakukan koreksi spesifik untuk mode ini (skip) |
| **STATUS_ONLY** | Keduanya gagal, atau salah satu kolom missing | Engine cuma andalkan `_status_class` × `interval_minutes` |

Auto-detect berdasarkan rasio non-NaN:

$$\text{ratio\_event} = \frac{|\{sd \in \text{shutdown\_dt} : \text{not NaN}\}| + |\{st \in \text{startup\_dt} : \text{not NaN}\}|}{2 \times N}$$

Jika `ratio_event ≥ 0.80` → EVENT. Else cek `ratio_num ≥ 0.80` → CUMULATIVE. Else → STATUS_ONLY.

**Edge case (Wave 11 hotfix #5/#6)**: kolom Huawei shutdown bisa berisi sentinel `0:00:00` (tahun < 2000 sentinel) yang mem-parse ke "hari ini midnight" → all-False mask. Sentinel ditangani di `_replace_sentinels()`: `{"-", "", "nan", "NaN", "None"}` → NaN. Plus ada **outer filter sentinel year < 2000** di main loop (Wave 11 hotfix #5).

### Langkah 5 — Estimate interval sampling (`_estimate_interval_minutes`)

$$\text{interval\_min} = \text{median}\left(\left\{(\text{ts}_{i+1} - \text{ts}_i) / 60 : i = 1, ..., N-1\right\}\right)$$

Fallback ke `5.0` menit jika data < 2 baris atau median ≤ 0. Data Huawei production = 5-menitan, jadi nilai ini biasanya tepat 5.0.

### Langkah 6 — Per-inverter availability (`_compute_inverter_availability`)

Untuk setiap inverter, group by `Inverter_ID`:

$$n_{\text{on}}   = \left|\{r : r.\_status\_class = \text{"ON"}\}\right|$$
$$n_{\text{down}} = \left|\{r : r.\_status\_class = \text{"DOWN"}\}\right|$$
$$\text{denom} = n_{\text{on}} + n_{\text{down}}$$

Jika `denom = 0` (semua TRANSITIONAL/UNKNOWN), inverter di-skip.

$$\boxed{\text{uptime\_pct} = \frac{100 \cdot n_{\text{on}}}{n_{\text{on}} + n_{\text{down}}}}$$

$$\text{downtime\_min} = n_{\text{down}} \cdot \text{interval\_min}$$

**Koreksi EVENT mode**: jika `mode = EVENT`, dan ada baris dengan `shutdown_time > startup_time` (= benar-benar tercatat event down), engine pakai upper bound waktu nyata:

```python
ev_down = (sd_sub > st_sub) & sd_sub.notna() & st_sub.notna()
if ev_down.any():
    down_rows = sub.loc[ev_down, "Start Time"]
    if len(down_rows) >= 2:
        delta_min = (down_rows.max() - down_rows.min()).total_seconds() / 60.0
        downtime_min = max(downtime_min, delta_min)
```

Jadi `downtime_min` akhirnya = `max(n_down × interval, delta_event_min)`. Ini mencegah under-count akibat sampling 5-menit kehilangan event pendek.

**Insight skeptis (dari Master Context line 695)**: koreksi EVENT mengasumsikan vendor menulis "waktu shutdown event terbaru". Jika ternyata field itu adalah "waktu shutdown kumulatif" tapi kebetulan terlihat seperti datetime, koreksi ini bisa over-correct. Engineer perlu spot-check 2-3 baris asli.

**Mapping severity** (`_severity_for_uptime`):

| Kondisi | Severity | Threshold breached |
|---|---|---|
| NaN | NORMAL | NaN |
| uptime < `critical_below` (default 90) | CRITICAL | 90 |
| uptime < `high_below` (default 95) | HIGH | 95 |
| uptime < `medium_below` (default 97) | MEDIUM | 97 |
| uptime < `info_below` (default 99) | INFO | 99 |
| uptime ≥ 99 | NORMAL | 99 |

Finding NORMAL **tidak di-emit** kecuali `emit_normal=true` di config (default false).

### Langkah 7 — Per-inverter operation log (`_compute_inverter_operation_log`)

Untuk setiap inverter, satu baris log dengan kolom `inverter_id, startup_time, shutdown_time, operation_duration_minutes, status`. Logic:
- `last_status_class` = klas status di baris terakhir (chronologically) per inverter
- Jika EVENT mode: `startup_dt = max(non-NaN startup)`, `shutdown_dt = max(non-NaN shutdown)`
- Duration logic berbeda per last_status_class:
  - ON: `duration = last_obs − startup_dt` (jam operasi sampai akhir data)
  - DOWN: jika `shutdown > startup`, `duration = shutdown − startup`
  - Lainnya: `duration = last_obs − startup_dt` (fallback)

Output disimpan di `self.last_inverter_log_df` untuk Cell 4 bridge.

### Langkah 8 — String-level proxy down (`_compute_string_proxy`) — **INTI HYBRID**

Inilah algoritma yang membuat istilah "hybrid" relevan. Karena tidak ada status per-string, engine **menebak string anomali** via sibling comparison. Parameter dari `m2e.string_proxy`:

| Parameter | Default | Penjelasan engineering |
|---|---|---|
| `pstr_zero_threshold_kw` | 0.1 | Power di bawah ini = string dianggap mati. 0.1 kW konservatif (sensor noise floor) |
| `sibling_median_active_kw` | 1.0 | Median sibling ≥ ini → timestamp "produktif" (filter awan tebal) |
| `min_active_siblings_pct` | 50 | ≥ 50% sibling aktif (> 0.1 kW) → timestamp "qualified" |
| `debounce_consecutive_steps` | 20 *(produksi IKN)* / 2 *(spec asli)* | Run kandidat ≥ debounce → genuine event (anti-glitch) |

**Algoritma** per inverter:

1. **Filter daylight per inverter**: ambil hanya baris dengan `_status_class = "ON"` dan timestamp ∈ `daylight_ts` (himpunan timestamp dimana minimal 1 inverter manapun ON).

   $$\text{daylight\_minutes\_inv} = \text{len}(\text{sub\_on}) \times \text{interval\_min}$$

2. **Hitung per-timestamp metrics across sibling PVs**:

   $$\text{sib\_median}_t = \text{median}\left(\{P_t^{PV_1}, P_t^{PV_2}, ..., P_t^{PV_n}\}\right)$$

   $$\text{active\_count}_t = \left|\{P_t^{PV_i} : P_t^{PV_i} > \text{pstr\_zero}\}\right|$$

   $$\text{active\_pct}_t = \frac{100 \cdot \text{active\_count}_t}{n_{\text{pv\_total}}}$$

3. **Qualified mask** per timestamp:

   $$\text{qualified}_t = (\text{sib\_median}_t \geq \text{sib\_med\_th}) \wedge (\text{active\_pct}_t \geq \text{min\_act\_pct})$$

4. **Per-PV candidate**:

   $$\text{cand}_{t,PV_i} = \text{qualified}_t \wedge (P_t^{PV_i} < \text{pstr\_zero}) \wedge (\text{PV}_i \notin \text{empty\_pv\_map}[inv])$$

5. **Find consecutive runs**: scan `cand` array, identifikasi tuple `(start_idx, end_idx)` dimana semua nilai True. Run dengan panjang ≥ `debounce` dianggap "qualified run".

6. **Aggregate event minutes**:

   $$\text{event\_minutes\_total} = \sum_{(a,b) \in \text{qualified\_runs}} (b - a + 1) \times \text{interval\_min}$$

7. **String uptime**:

   $$\boxed{\text{string\_uptime\_pct} = \max\left(0, 100 - \frac{100 \cdot \text{event\_minutes\_total}}{\max(\text{daylight\_minutes\_inv}, 10^{-9})}\right)}$$

8. **Severity mapping** identik dengan inverter (sama `_severity_for_uptime`).

**Filter EMPTY**: PV slot yang ada di `empty_pv_map[inv_id]` di-skip total — tidak di-emit sebagai finding apa pun. Ini berbeda dari "fault" — empty = by design (mis. WB01 hanya punya 18 string aktif fisik di 28 slot).

**Catatan engineering kritis**:
- TRANSITIONAL dan UNKNOWN sengaja **tidak masuk denominator** di per-inverter calc. Konsekuensi: malam hari (no sunlight → TRANSITIONAL) tidak menghukum uptime. Ini desain yang masuk akal: malam bukan downtime.
- Threshold `sibling_median_active_kw=1.0 kW` cocok untuk inverter Huawei dengan kapasitas string ~5 kW (Jinko 625W × 8 effective active modules). Untuk topology berbeda, bisa terlalu longgar/ketat (Master Context line 696).
- Wave 11 hotfix #10: PV slot yang ada di `empty_pv_map` di-skip di **main loop**, bukan hanya di sibling median. Bug sebelumnya menyebabkan ~910 false positive.

### Langkah 9 — AllStrings table (`_compute_all_strings_status`)

Selain finding (yang hanya emit non-NORMAL), engine emit tabel rapi setiap pasangan `(inverter_id, pv_string)` dengan kolom: `status, uptime_pct, downtime_minutes, event_minutes, n_events, daylight_minutes`. Status bisa salah satu dari:

| Status | Kondisi |
|---|---|
| `EMPTY` | PV slot ∈ `empty_pv_map[inv]` |
| `NO_DAYLIGHT` | Inverter tidak punya baris ON sama sekali |
| `NORMAL` | uptime ≥ `info_below` (99%) |
| `INFO` | 97% ≤ uptime < 99% |
| `MEDIUM` | 95% ≤ uptime < 97% |
| `HIGH` | 90% ≤ uptime < 95% |
| `CRITICAL` | uptime < 90% |

Total baris ≈ `n_inverter × n_pv_max` (mis. 193 × 28 = 5404 per snapshot Master Context).

Output disimpan di `self.last_all_strings_df`. Cell 4 menjembatani ke `sm_e.artifacts["AllStrings"]` agar masuk ke sheet xlsx `M2e_hybrid_AllStrings`.

---

## 3. Worked Example — Numerik Step-by-Step

**Dummy data** (2 inverter × 12 timestep × 5 PV, 5-menit interval, jam 10:00..10:55, ada di sheet `Raw_Data`):

| t | Time | INV01 status | INV01 PV1 | PV2 | PV3 | PV4 | PV5 | INV02 status | INV02 PV1-4 | PV5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 10:00 | Grid connected | 5.00 | 4.90 | 5.10 | 5.00 | 0 | Grid connected | 5.00 | 0 |
| 1 | 10:05 | Grid connected | 5.05 | 4.94 | 5.10 | 5.03 | 0 | Grid connected | 5.00 | 0 |
| 2 | 10:10 | Grid connected | 5.10 | 4.98 | 5.10 | 5.06 | 0 | Grid connected | 5.00 | 0 |
| 3 | 10:15 | Grid connected | 5.15 | 5.02 | **0.00** | 5.00 | 0 | Grid connected | 5.00 | 0 |
| 4 | 10:20 | Grid connected | 5.00 | 5.06 | **0.00** | 5.03 | 0 | **Shutdown command** | 0 | 0 |
| 5 | 10:25 | Grid connected | 5.05 | 4.90 | **0.00** | 5.06 | 0 | **Shutdown command** | 0 | 0 |
| 6 | 10:30 | Grid connected | 5.10 | 4.94 | **0.00** | 5.00 | 0 | **Shutdown command** | 0 | 0 |
| 7 | 10:35 | Grid connected | 5.15 | 4.98 | **0.00** | 5.03 | 0 | **Shutdown command** | 0 | 0 |
| 8 | 10:40 | Grid connected | 5.00 | 5.02 | **0.00** | 5.06 | 0 | Grid connected | 5.00 | 0 |
| 9 | 10:45 | Grid connected | 5.05 | 5.06 | 5.10 | 5.00 | 0 | Grid connected | 5.00 | 0 |
| 10 | 10:50 | Grid connected | 5.10 | 4.90 | 5.10 | 5.03 | 0 | Grid connected | 5.00 | 0 |
| 11 | 10:55 | Grid connected | 5.15 | 4.94 | 5.10 | 5.06 | 0 | Grid connected | 5.00 | 0 |

`empty_pv_map = {WB02-INV01: [5], WB02-INV02: [5]}` — PV5 EMPTY by design.

Threshold (Config sheet): `critical_below=90, high_below=95, medium_below=97, info_below=99, emit_normal=0, pstr_zero=0.1, sib_med_th=1.0, min_act_pct=50, debounce=2, interval=5, n_pv_total=5`.

### 3.1 Hitung per-inverter availability

**WB02-INV01**:
- n_on = 12, n_down = 0, denom = 12
- uptime = 100 × 12 / 12 = **100.00%** → NORMAL → tidak di-emit
- downtime = 0 × 5 = 0 menit

**WB02-INV02**:
- n_on = 8, n_down = 4, denom = 12
- uptime = 100 × 8 / 12 = **66.67%** → CRITICAL (< 90) → emit
- downtime = 4 × 5 = **20 menit**

✅ Excel cell `M2e_Availability!G7` = `CRITICAL`, `E7` = `66.67`, `F7` = `20`.

### 3.2 Hitung string proxy down untuk WB02-INV01

Karena INV01 semua ON (12 timestep), `sub_on = all 12 rows`. `daylight_minutes_inv = 12 × 5 = 60 menit`.

Per timestamp metrics:

| t | sib_median (PV1..5) | active_count | active_pct | qualified |
|---|---|---|---|---|
| 0 | median(5.00, 4.90, 5.10, 5.00, 0) = **5.00** | 4 | 80% | ✓ |
| 1 | median(5.05, 4.94, 5.10, 5.03, 0) = **5.03** | 4 | 80% | ✓ |
| 2 | median(5.10, 4.98, 5.10, 5.06, 0) = **5.06** | 4 | 80% | ✓ |
| 3 | median(5.15, 5.02, 0, 5.00, 0) = **5.00** | 3 | 60% | ✓ |
| 4..8 | similar, sib_median ≈ 5, active_pct = 60% | | | ✓ |
| 9..11 | sib_median ≈ 5.0..5.06, active_pct = 80% | | | ✓ |

Semua 12 timestep `qualified=1` karena sib_median ≥ 1.0 dan active_pct ≥ 50%.

**cand_PV3** = qualified ∧ (PV3 < 0.1):

| t | PV3 | cand_PV3 |
|---|---|---|
| 0..2 | 5.10 | 0 |
| 3..8 | **0.00** | **1** |
| 9..11 | 5.10 | 0 |

Ada 1 run: `(start=3, end=8)`, panjang = 8 − 3 + 1 = **6 timestep**. Karena 6 ≥ debounce=2, run ini "qualified".

- event_minutes_total = 6 × 5 = **30 menit**
- string_uptime_pct = max(0, 100 − 100 × 30 / 60) = **50.00%**
- Severity: 50 < 90 → **CRITICAL**

✅ Excel cell `M2e_Availability!F15` = `50.00`, `D15` = `30`, `E15` (n_events) = `1`, `G15` = `CRITICAL`.

**cand_PV1, PV2, PV4**: semua selalu > 0.1 → cand = 0 untuk semua t → tidak ada finding.

**PV5** untuk INV01: skip karena ∈ `empty_pv_map`. ✅ Excel `M2e_Availability!G17` = `EMPTY`.

### 3.3 Hitung string proxy down untuk WB02-INV02

INV02 punya 4 timestep DOWN (t=4..7), 8 timestep ON. `sub_on = 8 rows`. `daylight_minutes_inv = 8 × 5 = 40 menit`.

Pada `sub_on` (hanya t=0..3, 8..11), semua PV1-PV4 = 5.0 kW, PV5 = 0 kW.

sib_median = median(5, 5, 5, 5, 0) = 5.0 → ≥ 1.0 ✓
active_count = 4 → active_pct = 80% ✓
qualified = 1 untuk semua sub_on rows.

cand_PV3 = 1 ∧ (5.0 < 0.1) = 0 untuk semua → tidak ada cand_run. Same for PV1, PV2, PV4.

✅ Semua PV1-PV4 INV02 = `NORMAL` 100% uptime.
✅ PV5 INV02 = `EMPTY`.

### 3.4 Findings summary akhir

Yang akan di-emit ke sheet `Findings` (non-NORMAL):

| sub_module | inverter_id | pv_string | severity | value | message |
|---|---|---|---|---|---|
| M2e_inverter | WB02-INV02 | (none) | CRITICAL | 66.67 | inverter uptime 66.67% (n_on=8, n_down=4) |
| M2e_string_proxy | WB02-INV01 | PV3 | CRITICAL | 50.00 | WB02-INV01 PV3 proxy-down 30min/60min daylight (50.00% uptime) |

2 finding emitted. Sheet `M2e_AllStrings` mendapat 10 baris (2 inverter × 5 PV).

---

## 4. Pemetaan Python → Excel Formula

Lokasi semua formula: workbook `docs/M2_PV_Performance_Workbook.xlsx`, sheet `Helpers_M2e` dan `M2e_Availability`.

### 4.1 Sheet `Helpers_M2e` — derived columns per row

Setiap baris di `Helpers_M2e` mirror 1 baris di `Raw_Data` dengan kolom tambahan:

| Kolom | Formula Excel | Ekuivalen Python |
|---|---|---|
| `_status_class` (D) | `=IF(ISNUMBER(SEARCH("shutdown",LOWER(C)))+ISNUMBER(SEARCH("fault",LOWER(C))),"DOWN", IF(ISNUMBER(SEARCH("grid connected",LOWER(C))),"ON", IF(ISNUMBER(SEARCH("standby",LOWER(C))),"TRANSITIONAL","UNKNOWN")))` | `_classify_status(status, keymap)` |
| `sib_median_kW` (E) | `=MEDIAN(Raw_Data!D:H)` | `pv_vals.median(axis=1, skipna=True)` |
| `active_count` (F) | `=COUNTIF(Raw_Data!D:H, ">"&cfg_pstr_zero_threshold_kw)` | `(pv_vals > p_zero).sum(axis=1)` |
| `active_pct` (G) | `=100*F/cfg_n_pv_total_in_workbook` | `100 * active_count / n_pv_total` |
| `qualified` (H) | `=IF(AND(E>=cfg_sibling_median_active_kw, G>=cfg_min_active_siblings_pct),1,0)` | `(sib_median >= sib_med_th) & (active_pct >= min_act_pct)` |
| `is_on` (I) | `=IF(D="ON",1,0)` | `(_status_class == "ON")` |
| `cand_PV<n>` | `=IF(AND(I=1, H=1, Raw_Data!<col><n><.1),1,0)` | `qualified & (pv_series < p_zero) & is_on` |
| `run_id_PV<n>` | `=IF(A<>prev_A, IF(cand=1, MAX(prev_runids)+1, 0), IF(AND(cand=1, prev_cand=0), prev_runid+1, prev_runid))` | Run-counter increments on 0→1 transitions per group |
| `run_len_PV<n>` | `=IF(cand=1, COUNTIFS(inv_range, this_inv, runid_range, this_runid, cand_range, 1), 0)` | Run length lookup by (inverter, run_id) |
| `in_event_PV<n>` | `=IF(AND(cand=1, run_len>=cfg_debounce),1,0)` | Final debounce filter |

### 4.2 Sheet `M2e_Availability` — agregat per inverter & per string

**Section A — per inverter** (rows 6-7):

| Kolom | Formula |
|---|---|
| `n_on` | `=COUNTIFS(Helpers_M2e!$A$5:$A$28, A6, Helpers_M2e!$D$5:$D$28, "ON")` |
| `n_down` | `=COUNTIFS(Helpers_M2e!$A$5:$A$28, A6, Helpers_M2e!$D$5:$D$28, "DOWN")` |
| `denom` | `=B6+C6` |
| `uptime_pct` | `=IF(D6=0, NA(), 100*B6/D6)` |
| `downtime_min` | `=C6*cfg_interval_minutes` |
| `severity` | Nested `IF` 5-level (NA → NO_DATA, < 90 → CRITICAL, < 95 → HIGH, < 97 → MEDIUM, < 99 → INFO, else → NORMAL) |
| `threshold_breached` | Mirror severity tapi return nilai `cfg_*_below` |
| `message` | `="inverter uptime "&TEXT(E6,"0.00")&"% (n_on="&B6&", n_down="&C6&")"` |

**Section B — per string** (rows 13-22):

| Kolom | Formula |
|---|---|
| `daylight_minutes_inv` | `=COUNTIFS(Helpers!$A$5:$A$28, A13, Helpers!$I$5:$I$28, 1) * cfg_interval_minutes` |
| `event_minutes` | `=COUNTIFS(Helpers!$A$5:$A$28, A13, Helpers!$<inevent_col>$5:$<inevent_col>$28, 1) * cfg_interval_minutes` |
| `n_events` | `=SUMPRODUCT((inv_range=A13) * (in_event_range=1) * ((prev_in_event_range=0) + (inv_range<>prev_inv_range) >= 1))` |
| `string_uptime_pct` | `=IF(C=0, NA(), MAX(0, 100 - 100*D/C))` |
| `severity` | Nested `IF` (is_empty → EMPTY, daylight=0 → NO_DAYLIGHT, else uptime threshold mapping) |
| `is_empty` | `=IFERROR(IF(ISNUMBER(SEARCH(","&pv_n&",", ","&VLOOKUP(inv, EmptyPVMap, 2, FALSE)&",")),1,0),0)` |

### 4.3 Conditional formatting

Cell warna otomatis di kolom severity:
- CRITICAL → merah `#E06666`
- HIGH → oranye `#F6B26B`
- MEDIUM → kuning `#FFD966`
- INFO → biru muda `#A4C2F4`
- NORMAL → hijau `#B6D7A8`
- EMPTY → abu-abu `#DDDDDD`

---

## 5. Edge Cases & Limitasi Translasi

### 5.1 Edge cases yang ditangani Python tapi tidak/sebagian di Excel

| Edge case | Python | Excel | Mitigasi |
|---|---|---|---|
| Sentinel `"-", "", "nan"` di shutdown/startup → NaN | `_replace_sentinels` | Tidak ada di workbook (mode STATUS_ONLY default — Excel tidak menggunakan EVENT mode) | Worksheet ini hanya STATUS_ONLY mode. Tidak loss kalau dataset Anda EVENT mode dan ingin koreksi `delta_event`. Saya berikan formula opsional di bagian 5.3. |
| Sentinel year < 2000 (Wave 11 hotfix #5) | Filter eksternal di main loop | Tidak ada | Manual: filter Raw_Data sebelum paste |
| Title Case vs lowercase PV column names (PV1-14 vs PV15-28) | `transformations.py` normalize | Excel mengasumsikan PV1 Power(kW) lowercase | Manual normalization sebelum paste |
| Inverter status "Grid connected : power limited" → ON | Substring match ✓ | Substring SEARCH ✓ | OK |
| `_estimate_interval_minutes` median | Auto-detect | Hardcoded `cfg_interval_minutes` | User must set Config; jika data tidak 5-min, ubah Config |
| EMPTY_PV_MAP 244 entries | YAML load otomatis | Hanya 4 entri di sheet `EmptyPVMap` (dummy) | Untuk produksi: extend `EmptyPVMap` sheet dari `config/strings.yaml` |
| Multi-day dataset (data dates > 1) | `DATA_DATESTR` auto-detect range | Workbook dirancang per-hari | Run workbook per-hari; gabung di Python jika perlu |

### 5.2 Formula yang berbeda dari Python tapi seharusnya ekuivalen

| Formula | Python | Excel | Catatan |
|---|---|---|---|
| sib_median | `df[pv_cols].median(axis=1, skipna=True)` | `MEDIAN(D:H)` | Excel MEDIAN ignore blank tapi treat 0 sebagai value. **DUMMY**: PV5=0 selalu ikut median, sama dengan Python yang juga include 0. Untuk produksi yang PV5 = empty di YAML, Python juga include 0 (kolom-nya ada di pv_cols). Equivalent. |
| Run detection | Per-inverter scan run_lens list | `run_id` increments per group + `COUNTIFS` | Equivalent untuk single-run-per-PV case. Multi-run dalam 1 hari sama-sama dihitung. |
| `n_events` | `len(qualified_runs)` | `SUMPRODUCT` count of transitions 0→1 within group | Equivalent. |
| Severity | Nested if-elif | Nested IF | Equivalent. |

### 5.3 Hal yang TIDAK ada di Excel saat ini (opsional implementasi)

1. **EVENT mode shutdown_time correction**. Python pakai max(`n_down × interval`, `delta_event_min`). Excel saat ini cuma `n_down × interval`.
   - Jika dataset Anda punya kolom `Inverter shutdown time` dan `Inverter startup time` valid:
     - Tambah kolom helper `event_down_min` = `(MAX(shutdown_time) - MIN(startup_time)) * 24 * 60` per inverter
     - `downtime_min` = `MAX(C * interval, event_down_min)`

2. **`UNKNOWN` status warning + top-20 list**. Python warn ke stderr. Excel tidak — user perlu spot-check sendiri kolom `status_raw` vs `_status_class` di `Helpers_M2e`.

3. **`pv_max_allowed=28` enforcement**. Python `_detect_pv_power_cols` filter PV column dengan index ≤ 28. Excel hanya punya PV1..PV5 di workbook ini. Untuk produksi 28 PV per inverter, perlu extend Raw_Data sheet + Helpers_M2e (lebih banyak kolom cand/runid/runlen/in_event).

4. **Multi-source POA fan-out**. Tidak relevan untuk M2e (M2e tidak pakai POA). Hanya untuk M2b/M2a.

5. **Wave 9 Hampel preprocessing**. M2e tidak menerapkan Hampel — itu eksklusif untuk M2b detectors. Excel tidak perlu replicate untuk M2e.

---

## 6. Cross-Check vs Master Context Spec

| Aspek | Master Context §4.5 spec | Implementasi `availability.py` | Match? |
|---|---|---|---|
| Threshold severity | Critical < 90, High 90-95, Medium 95-97, INFO 97-99, NORMAL > 99 | Critical < 90, HIGH 90-95, MEDIUM 95-97, INFO 97-99, NORMAL ≥ 99 | ✅ exact match |
| Definisi "down" per string | P_string < 5% dari P_expected_string, saat POA > 50 W/m², ≥ 2 timestep | P_string < `pstr_zero_threshold` (kW absolut), saat `qualified` mask (sibling median + active%), ≥ `debounce` timestep | ⚠ konseptual sama, implementasi berbeda |
| POA threshold 50 W/m² | Required di spec | TIDAK dipakai — pakai `sibling_median_active_kw` sebagai proxy POA presence | ⚠ proxy (tidak butuh meteo data) |
| P_expected dari pvlib | Required di spec | TIDAK ada — pakai sibling median | ⚠ kompromi |
| Debounce 2 timestep | Spec default 2 | DEFAULT_M2_CONFIG dulu 2, kemudian production-tuned ke 20 | ⚠ override IKN |
| EMPTY by design distinction | Tidak dibahas spec | Innovasi dari notebook v1.2 (244 entri EMPTY_PV_MAP) | ✅ nilai tambah |

**Trade-off**: implementasi avoid pvlib dependency untuk M2e — bisa langsung dipakai sejak hari pertama commissioning (zero data prerequisites). Spec ideal butuh POA + Tcell + datasheet yang baru tersedia setelah Sprint 3 (instrumentation).

---

## 7. Verification Log

Saya jalankan tiga verifikasi sebelum publikasi dokumen ini:

1. **Python reference run** dengan `pv_pipeline/availability.py` di dummy data → output `availability_test_run.txt`.
2. **Excel formulas render via LibreOffice** → output `M2_PV_Performance_Workbook.xlsx` di-convert via `soffice --convert-to xlsx`.
3. **Cell-by-cell diff** antara Python ref dan Excel render.

Hasil:

| Kasus uji | Python | Excel | Match |
|---|---|---|---|
| WB02-INV01 inverter uptime | 100.00% NORMAL (filtered) | 100.00 NORMAL | ✅ |
| WB02-INV02 inverter uptime | 66.67% CRITICAL (downtime 20min) | 66.67 CRITICAL 20min | ✅ |
| WB02-INV01 PV3 string uptime | 50.00% CRITICAL (event 30min / daylight 60min, 1 event) | 50.00 CRITICAL 30/60 1 event | ✅ |
| WB02-INV02 PV3 string uptime | 100% NORMAL (DOWN timesteps excluded) | 100 NORMAL | ✅ |
| PV5 status both inverters | EMPTY (NaN) | EMPTY (blank) | ✅ |

---

## 8. Rekomendasi Penggunaan Workbook

1. **Replace dummy data dengan data aktual**:
   - Sheet `Raw_Data`: paste over kolom `Inverter_ID, Start Time, Inverter status, PV1..PVn Power(kW)` dari `combined_df` Python (export via `df.to_excel`).
   - Sheet `EmptyPVMap`: paste/replicate dari `config/strings.yaml` (244 entri) — gunakan formula `=TEXTJOIN(",", TRUE, ...)` untuk convert list YAML ke CSV string.
   - Sheet `Config`: sesuaikan `debounce_consecutive_steps` ke produksi value 20 (untuk IKN).

2. **Extend ke 28 PV string**:
   - Sheet `Raw_Data`: tambah kolom PV6 Power(kW) sampai PV28 Power(kW).
   - Sheet `Helpers_M2e`: tambah 4 kolom per PV baru (cand, run_id, run_len, in_event). Workbook saat ini di-design untuk PV1..PV5 saja.
   - Cell `cfg_n_pv_total_in_workbook` di Config: ubah dari 5 ke 28.

3. **Extend ke multiple inverter** (>2):
   - Sheet `M2e_Availability` Section A: tambah row per inverter (copy formula row 6 dan adjust inverter_id).
   - Section B: 5 row per inverter (PV1..PV5).

4. **Override debounce per use case**:
   - Spec asli (2026-05-08): debounce = 2 → quick detection, more sensitive
   - Production IKN (Wave 11): debounce = 20 → 1h40m persistence, less false positive
   - Tradeoff: lower debounce = catch shorter faults, more noise. Tune sesuai sensor noise floor.

---

## 9. Pertanyaan untuk Iterasi Berikutnya (M2bPeerZScore)

Sebelum maju ke iterasi 3, beberapa hal yang akan saya tanyakan:
1. POA value dummy untuk M2b. Saya pakai POA = 800 W/m² (clear-sky proxy) atau load 1 hari real POA dari `raw data input/POA PLTS IKN 2026.xlsx`?
2. Voc_actual estimation. M2bPeerZScore butuh `voc_ratio` untuk high_R rule. Apakah dummy harus include skenario sunrise/sunset (I→0)?
3. Multi-source POA fan-out (5 sources). Apakah workbook perlu sheet per source, atau cukup 1 source default (clear-sky Ineichen)?

---

## Sources

- `pv_pipeline/availability.py` (773 baris) — full read, semua fungsi `_*` dan `M2eAvailability.run()`
- `pv_pipeline/string_config.py` (92 baris) — `load_empty_pv_map`, `sanitize_empty_pv_map`, `get_empty_pv_map`
- `pv_pipeline/core.py` baris 1-127 — `Severity`, `M2Finding`, `load_empty_pv_map` (Wave 11 hotfix #5)
- `config/m2_config.yaml` — section `m2e.*` (severity_thresholds, string_proxy, shutdown_time_detection)
- `config/strings.yaml` — format YAML EMPTY_PV_MAP (245 baris, 244 entri inverter)
- `M2_PV_Performance_Master_Context.docx` — §4.5 String Availability, §4.5.1 Definisi "Down", sprint summary "Inti perhitungan: M2eAvailability.run" (lines 626-697 di teks ekstrak)
- Notebook `20260514stringmap_v1.5.ipynb` Cell 4 — instantiation `sm_e = M2eAvailability()` + bridge `sm_e.last_all_strings_df` → `sm_e.artifacts["AllStrings"]`
- Verified live: Python ref run + Excel formula render via LibreOffice cell-by-cell compare
