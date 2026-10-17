"""Peta riwayat cleaning modul PV di atas layout PLTS -- satu HTML::

    python peta_progress_cleaning.py "F:\\Downloads part 2\\raw data input\\Report & Schedule Cleaning PLTS IKN.xlsx"

Jalankan ulang tiap checklist diperbarui: semua centang di semua sheet
``STS{n}`` dibaca ulang lewat ``pv_pipeline.m2a.cleaning_report``. Tampilan ada
di ``peta_progress_cleaning_templat.html``; gayanya mengikuti peta foto drone
di repo cv-drone-plts (``alat/peta_foto_drone.py``).

Cycle = sheet checklist (``STS1 (2026 Cycle 2)`` dst.), definisi tim lapangan
sendiri. Progress cycle dihitung terhadap jadwal sheet (rentang kolom
tanggalnya), jadi sheet tanpa satu centang pun tetap tampil 0 %.

Posisi string = pusat meja dari DXF (``table_lat/table_lon`` di
``config/string_geometry.csv``). Untuk string tanpa pusat meja dipakai label:
di WB01-WB02 label ~ pusat meja; di WB03-WB10 label ada di ujung barat meja,
jadi digeser L/2 x cos(cross_slope) ke timur, L = 14,98 m.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
import warnings
from datetime import date
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd

from pv_pipeline.m2a.cleaning_report import load_cleaning_report, load_cleaning_schedule

ROOT = Path(__file__).resolve().parent
GEOMETRY_PATH = ROOT / "config" / "string_geometry.csv"
KELUARAN_PATH = ROOT / "docs" / "Peta_Progress_Cleaning_PLTS.html"
TEMPLAT_PATH = ROOT / "peta_progress_cleaning_templat.html"

PANJANG_MEJA_M = 14.98          # WB03-WB10; untuk geser label ujung barat -> pusat
GAMBAR_MEJA_M = (13.6, 4.3)     # sedikit lebih kecil dari meja asli agar celahnya terlihat
_M_PER_DEG = 111_320.0          # hampiran equirectangular, sama dengan peta foto drone
_BULAN = dict(enumerate("Jan Feb Mar Apr Mei Jun Jul Agu Sep Okt Nov Des".split(), start=1))


def _meter(lat, lon, lat0: float, lon0: float):
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    return (lon - lon0) * _M_PER_DEG * math.cos(math.radians(lat0)), (lat - lat0) * _M_PER_DEG


def posisi_meja(geom: pd.DataFrame) -> pd.DataFrame:
    """Geometri string -> [string, inverter_id, st, wb, x, y] dalam meter lokal (y ke utara)."""
    lat0, lon0 = float(geom["lat"].mean()), float(geom["lon"].mean())
    x, y = _meter(geom["table_lat"].fillna(geom["lat"]), geom["table_lon"].fillna(geom["lon"]), lat0, lon0)
    wb = geom["inverter_id"].str[2:4].astype(int).to_numpy()
    geser = geom["table_lat"].isna().to_numpy() & (wb > 2)
    cs = np.radians(geom["cross_slope_deg"].fillna(0.0).to_numpy(float))
    x = x + np.where(geser, PANJANG_MEJA_M / 2 * np.cos(cs), 0.0)
    st = geom["st"].astype(int)
    return pd.DataFrame({
        "string": geom["inverter_id"] + "-ST" + st.map("{:02d}".format),
        "inverter_id": geom["inverter_id"], "st": st, "wb": wb, "x": x, "y": y,
    })


def gabung_layout(events: pd.DataFrame, pos: pd.DataFrame) -> pd.DataFrame:
    """Beri tiap centang kunci ``string``; gagal bila ada centang tanpa meja di layout."""
    ev = events.assign(string=events["inverter_id"] + "-ST" + events["st"].astype(int).map("{:02d}".format))
    hilang = sorted(set(ev["string"]) - set(pos["string"]))
    if hilang:
        raise ValueError(f"{len(hilang)} string di checklist tidak ada di layout: {hilang[:10]}")
    return ev


def ringkas_cycle(events: pd.DataFrame, jadwal: pd.DataFrame) -> pd.DataFrame:
    """Satu baris per sheet: jadwal vs realisasi (string unik, centang, hari kerja)."""
    g = events.groupby("sheet")
    real = pd.DataFrame({
        "dibersihkan": events.drop_duplicates(["sheet", "inverter_id", "st"]).groupby("sheet").size(),
        "centang": g.size(),
        "hari_kerja": g["date"].nunique(),
        "pertama": g["date"].min(),
        "terakhir": g["date"].max(),
    })
    out = jadwal.merge(real, left_on="sheet", right_index=True, how="left")
    for k in ("dibersihkan", "centang", "hari_kerja"):
        out[k] = out[k].fillna(0).astype(int)
    out["pct"] = (100.0 * out["dibersihkan"] / out["n_strings"]).round(1)
    return out.sort_values(["wb", "start"], ignore_index=True)


# --- format ------------------------------------------------------------------
def _ribuan(n) -> str:
    return f"{n:,.0f}".replace(",", ".")


def _tgl(t, tahun=True) -> str:
    t = pd.Timestamp(t)
    return f"{t.day} {_BULAN[t.month]}" + (f" {t.year}" if tahun else "")


def _rentang(a, b) -> str:
    if pd.isna(a):
        return "&ndash;"
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    if a == b:
        return _tgl(a)
    if a.year != b.year:
        return f"{_tgl(a)} &ndash; {_tgl(b)}"
    return f"{a.day if a.month == b.month else _tgl(a, False)} &ndash; {_tgl(b)}"


def _gantt(ev: pd.DataFrame, cyc: pd.DataFrame, disusun: date, wbs) -> str:
    """Linimasa: pita = jendela jadwal tiap sheet, batang = string per hari kerja."""
    a = min(cyc["start"].min(), ev["date"].min()).replace(day=1)
    b = max(cyc["end"].max(), pd.Timestamp(disusun)) + pd.Timedelta(days=6)
    W, KIRI, KANAN, ATAS, BARIS = 1000, 58, 10, 30, 32
    ppd = (W - KIRI - KANAN) / (b - a).days
    H = ATAS + BARIS * len(wbs) + 8
    X = lambda t: KIRI + (pd.Timestamp(t) - a).days * ppd  # noqa: E731
    baris_wb = {w: i for i, w in enumerate(wbs)}
    out = [f'<svg id="gantt" viewBox="0 0 {W} {H}" role="img" aria-label="Jadwal dan hari kerja cleaning per WB">']
    for i, m in enumerate(pd.date_range(a, b, freq="MS")):
        x = X(m)
        lab = _BULAN[m.month] + (f" {m.year % 100:02d}" if m.month == 1 or i == 0 else "")
        out.append(f'<path class="gr{" th" if m.month == 1 else ""}" d="M{x:.1f} {ATAS - 6}V{H - 8}"/>'
                   f'<text class="ax" x="{x + 3:.1f}" y="{ATAS - 12}">{lab}</text>')
    for w, i in baris_wb.items():
        y = ATAS + i * BARIS
        out.append(f'<text class="wbn" x="0" y="{y + BARIS / 2 + 4:.0f}">{w}</text>'
                   f'<path class="garis" d="M{KIRI} {y + BARIS - 1}H{W - KANAN}"/>')
    for r in cyc.itertuples():
        y = ATAS + baris_wb[f"WB{r.wb:02d}"] * BARIS
        x0, x1 = X(r.start), X(r.end + pd.Timedelta(days=1))
        judul = (f"{html.escape(r.sheet)} &#183; jadwal {_rentang(r.start, r.end)} &#183; "
                 f"{_ribuan(r.dibersihkan)}/{_ribuan(r.n_strings)} string ({str(r.pct).replace('.', ',')} %)")
        out.append(f'<rect class="jw" x="{x0:.1f}" y="{y + 4}" width="{x1 - x0:.1f}" height="{BARIS - 9}">'
                   f'<title>{judul}</title></rect>')
    per = ev.groupby(["wb", "date", "sheet"]).size().rename("n").reset_index()
    nmax = per["n"].max()
    for r in per.itertuples():
        y0 = ATAS + baris_wb[f"WB{r.wb:02d}"] * BARIS + BARIS - 5
        h = max(2.0, (BARIS - 9) * r.n / nmax)
        d = (r.date - ev["date"].min()).days
        out.append(f'<rect class="kj" data-d="{d}" x="{X(r.date):.1f}" y="{y0 - h:.1f}" width="{max(1.6, ppd):.1f}" '
                   f'height="{h:.1f}"><title>{_tgl(r.date)} &#183; WB{r.wb:02d} &#183; {r.n} string &#183; '
                   f'{html.escape(r.sheet)}</title></rect>')
    xh = X(disusun)
    out.append(f'<path class="kini" d="M{xh:.1f} {ATAS - 6}V{H - 8}"/>'
               f'<text class="ax kini-t" x="{xh - 3:.1f}" y="{H - 1}">hari ini</text></svg>')
    return "".join(out)


def bangun_html(ev: pd.DataFrame, pos: pd.DataFrame, jadwal: pd.DataFrame, sumber: Path,
                disusun: date) -> str:
    cyc = ringkas_cycle(ev, jadwal)
    t0 = ev["date"].min()
    hari = lambda t: int((pd.Timestamp(t) - t0).days)  # noqa: E731
    total = len(pos)
    wbs = [f"WB{w:02d}" for w in sorted(pos["wb"].unique())]

    # kerangka peta dalam meter lokal; y ke bawah = selatan (sama dengan peta foto drone)
    X0, X1 = pos["x"].min() - 40, pos["x"].max() + 40
    Y0, Y1 = pos["y"].min() - 110, pos["y"].max() + 40
    W, H = X1 - X0, Y1 - Y0
    sx = lambda x: x - X0  # noqa: E731
    sy = lambda y: Y1 - y  # noqa: E731
    label_wb = "".join(f'<text x="{sx(s["x"].mean()):.0f}" y="{sy(s["y"].mean()):.0f}">WB{w:02d}</text>'
                       for w, s in pos.groupby("wb"))
    sb = H - 45
    svg_peta = (f'<svg id="peta" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
                f'aria-label="Kondisi cleaning {_ribuan(total)} string per tanggal">'
                f'<rect class="batas" x="{sx(pos["x"].min()) - 14:.1f}" y="{sy(pos["y"].max()) - 8:.1f}" '
                f'width="{pos["x"].max() - pos["x"].min() + 28:.1f}" height="{pos["y"].max() - pos["y"].min() + 16:.1f}"/>'
                f'<g id="meja"></g><g class="wbl">{label_wb}</g>'
                f'<g class="sb"><path d="M40 {sb:.0f}h100M40 {sb - 10:.0f}v20M140 {sb - 10:.0f}v20"/>'
                f'<text x="90" y="{sb - 18:.0f}">100 m</text></g>'
                f'<g class="sb"><path d="M{W - 40:.0f} {sb + 10:.0f}v-60M{W - 50:.0f} {sb - 35:.0f}l10 -15l10 15"/>'
                f'<text x="{W - 40:.0f}" y="{sb - 60:.0f}">U</text></g></svg>')

    hari_str = ev.groupby("string")["date"].apply(lambda s: sorted({hari(t) for t in s}))
    data_str = [[round(sx(r.x), 1), round(sy(r.y), 1), r.string, wbs.index(f"WB{r.wb:02d}"),
                 hari_str.get(r.string, [])] for r in pos.itertuples()]
    hari_kerja = sorted({hari(t) for t in ev["date"]})

    # tabel cycle (bagian 02)
    baris_c = []
    for r in cyc.itertuples():
        berjalan = r.end >= pd.Timestamp(disusun)
        pct = str(r.pct).replace(".", ",")
        putaran = f"{r.centang / r.dibersihkan:.1f}&times;".replace(".", ",") if r.dibersihkan else "&ndash;"
        baris_c.append(
            f'<tr{" class=hi" if berjalan else ""}><td>{html.escape(r.sheet)}'
            f'{" <span class=tag>berjalan</span>" if berjalan else ""}</td>'
            f'<td class="n">WB{r.wb:02d}</td><td>{_rentang(r.start, r.end)}</td>'
            f'<td>{_rentang(r.pertama, r.terakhir)}</td><td class="n">{r.hari_kerja}</td>'
            f'<td class="n"><b>{_ribuan(r.dibersihkan)}</b> / {_ribuan(r.n_strings)}</td>'
            f'<td class="n"><span class="bar"><i style="width:{min(r.pct, 100):.1f}%"></i></span>{pct}&nbsp;%</td>'
            f'<td class="n">{putaran}</td></tr>')

    # rincian per tanggal (bagian 04), terbaru di atas
    baris_t = []
    for (t, w, sh), s in ev.groupby(["date", "wb", "sheet"]):
        inv = s.groupby("inverter_id").size()
        teks = " &#183; ".join(f"{i[-5:]}&nbsp;{n}" for i, n in inv.items())
        baris_t.append(f'<tr><td class="n">{_tgl(t)}</td><td class="n">WB{w:02d}</td><td>{html.escape(sh)}</td>'
                       f'<td class="n"><b>{len(s)}</b></td><td class="m">{teks}</td></tr>')

    pernah = ev["string"].nunique()
    kosong = cyc[cyc["dibersihkan"] == 0]
    teks_kosong = "".join(
        f"<p><b>{html.escape(r.sheet)}</b> dijadwalkan {_rentang(r.start, r.end)} untuk "
        f"{_ribuan(r.n_strings)} string, tetapi tidak satu pun dicentang.</p>" for r in kosong.itertuples())
    belum_wb = pos[~pos["string"].isin(ev["string"])].groupby("wb").size()
    teks_belum = ", ".join(f"WB{w:02d} {_ribuan(n)}" for w, n in belum_wb.sort_values(ascending=False).items())

    nilai = dict(
        sumber=html.escape(sumber.name), total=_ribuan(total),
        n_centang=_ribuan(len(ev)), n_sheet=len(jadwal), n_hari=_ribuan(len(hari_kerja)),
        t_awal=_tgl(t0), t_akhir=_tgl(ev["date"].max()), disusun=_tgl(disusun),
        n_pernah=_ribuan(pernah), pct_pernah=f"{100 * pernah / total:.0f}",
        n_belum=_ribuan(total - pernah), teks_belum=teks_belum, teks_kosong=teks_kosong,
        svg_peta=svg_peta, svg_gantt=_gantt(ev, cyc, disusun, wbs),
        baris_c="".join(baris_c), baris_t="".join(reversed(baris_t)),
        data_str=json.dumps(data_str, ensure_ascii=False, separators=(",", ":")),
        data_wb=json.dumps(wbs), data_kerja=json.dumps(hari_kerja),
        t0_iso=t0.strftime("%Y-%m-%d"), d_kini=hari(disusun),
        meja_w=GAMBAR_MEJA_M[0], meja_h=GAMBAR_MEJA_M[1],
    )
    return Template(TEMPLAT_PATH.read_text(encoding="utf-8")).substitute(nilai)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("checklist", type=Path, help="Report & Schedule Cleaning PLTS IKN.xlsx")
    ap.add_argument("--geometri", type=Path, default=GEOMETRY_PATH)
    ap.add_argument("--keluaran", type=Path, default=KELUARAN_PATH)
    a = ap.parse_args(argv)

    pos = posisi_meja(pd.read_csv(a.geometri))
    with warnings.catch_warnings():
        # Peta memakai nomor ST (sisi lapangan), bukan nomor PV inverter, jadi
        # peringatan "tanpa mapping ST->PV" untuk WB03-WB10 tidak relevan di sini.
        warnings.filterwarnings("ignore", message=r".*tanpa mapping ST->PV")
        events = load_cleaning_report(str(a.checklist), {})
    ev = gabung_layout(events, pos)
    jadwal = load_cleaning_schedule(str(a.checklist))
    # WITA eksplisit: di Colab (UTC) date.today() mundur sehari sebelum 08.00 WITA.
    hari_ini = pd.Timestamp.now(tz="Asia/Makassar").date()
    teks = bangun_html(ev, pos, jadwal, a.checklist, hari_ini)
    a.keluaran.parent.mkdir(parents=True, exist_ok=True)
    a.keluaran.write_text(teks, encoding="utf-8")
    print(f"{len(ev):,} centang dari {len(jadwal)} sheet, {ev['string'].nunique():,}/{len(pos):,} string "
          f"pernah dibersihkan, {ev['date'].min().date()} s.d. {ev['date'].max().date()}")
    print(f"-> {a.keluaran} ({a.keluaran.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
