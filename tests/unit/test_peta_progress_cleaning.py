"""Tests peta_progress_cleaning (peta riwayat cleaning di atas layout).

Kenapa penting:
- Centang yang tidak menemukan mejanya akan lenyap dari peta tanpa suara,
  dan string itu terlihat "belum pernah dibersihkan" padahal sudah.
- Progress cycle dihitung terhadap JADWAL sheet, bukan terhadap event:
  sheet yang tak satu pun dicentang (STS7 asli) harus tampil 0 %, bukan hilang.
- Posisi meja: 29 string tidak punya pusat meja DXF; label WB03-WB10 ada di
  ujung barat meja, jadi tanpa geser ke timur string tertukar tetangganya.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from peta_progress_cleaning import gabung_layout, posisi_meja, ringkas_cycle


def _geom(rows):
    return pd.DataFrame(rows, columns=[
        "inverter_id", "st", "lat", "lon", "cross_slope_deg", "table_lat", "table_lon",
    ])


def _events(rows):
    return pd.DataFrame(rows, columns=["date", "inverter_id", "wb", "st", "sheet"]).assign(
        date=lambda d: pd.to_datetime(d["date"]),
    )


GEOM = _geom([
    ["WB01-INV01", 1, -0.99, 116.63, 0.0, -0.99, 116.63],
    ["WB01-INV01", 2, -0.99, 116.6302, 0.0, None, None],
    ["WB08-INV01", 1, -0.98, 116.64, 0.0, -0.98, 116.64007],
    ["WB08-INV01", 2, -0.98, 116.6402, 60.0, None, None],
])


def test_posisi_meja_pakai_pusat_dxf_lalu_geser_label_barat():
    pos = posisi_meja(GEOM).set_index("string")
    ref = posisi_meja(GEOM.assign(table_lat=GEOM["lat"], table_lon=GEOM["lon"])).set_index("string")
    # WB01 tanpa pusat meja: label = pusat (Phase One), tidak digeser.
    assert pos.loc["WB01-INV01-ST02", "x"] == pytest.approx(ref.loc["WB01-INV01-ST02", "x"])
    # WB08 tanpa pusat meja: label ujung barat -> geser L/2*cos(cross) ke timur.
    geser = pos.loc["WB08-INV01-ST02", "x"] - ref.loc["WB08-INV01-ST02", "x"]
    assert geser == pytest.approx(14.98 / 2 * math.cos(math.radians(60.0)), abs=0.01)
    assert pos.loc["WB08-INV01-ST02", "y"] == pytest.approx(ref.loc["WB08-INV01-ST02", "y"])


def test_gabung_layout_menolak_centang_tanpa_meja():
    ev = _events([
        ["2026-08-08", "WB08-INV01", 8, 1, "STS8"],
        ["2026-08-08", "WB08-INV01", 9, 99, "STS8"],
    ])
    with pytest.raises(ValueError, match="WB08-INV01-ST99"):
        gabung_layout(ev, posisi_meja(GEOM))


def test_ringkas_cycle_terhadap_jadwal_termasuk_sheet_kosong():
    ev = _events([
        ["2025-03-01", "WB01-INV01", 1, 1, "STS1 (2025)"],
        ["2025-09-01", "WB01-INV01", 1, 1, "STS1 (2025)"],
        ["2025-09-02", "WB01-INV01", 1, 2, "STS1 (2025)"],
    ])
    jadwal = pd.DataFrame([
        ["STS1 (2025)", 1, 2, "2025-03-01", "2025-12-31"],
        ["STS7", 7, 418, "2026-03-20", "2026-04-05"],
    ], columns=["sheet", "wb", "n_strings", "start", "end"]).assign(
        start=lambda d: pd.to_datetime(d["start"]), end=lambda d: pd.to_datetime(d["end"]),
    )
    c = ringkas_cycle(ev, jadwal).set_index("sheet")
    assert c.loc["STS1 (2025)", "dibersihkan"] == 2
    assert c.loc["STS1 (2025)", "centang"] == 3
    assert c.loc["STS1 (2025)", "pct"] == 100.0
    assert c.loc["STS1 (2025)", "hari_kerja"] == 3
    assert c.loc["STS7", "dibersihkan"] == 0
    assert c.loc["STS7", "pct"] == 0.0
    assert pd.isna(c.loc["STS7", "pertama"])
