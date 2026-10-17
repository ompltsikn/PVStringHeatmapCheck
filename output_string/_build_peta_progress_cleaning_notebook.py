"""Builder Peta_Progress_Cleaning.ipynb.

Notebook menjalankan ``peta_progress_cleaning.py`` di Google Colab: checklist
``Report & Schedule Cleaning PLTS IKN.xlsx`` diunduh dari folder Drive
**raw data input**, kode diambil dari GitHub, hasilnya satu HTML yang bisa
diunduh lalu dibuka di browser biasa.

Edit builder ini lalu jalankan:
    python output_string/_build_peta_progress_cleaning_notebook.py
"""
from __future__ import annotations

import json
from pathlib import Path


OUT = Path(__file__).parent / "Peta_Progress_Cleaning.ipynb"

MD_INTRO = '''# Peta Progress Cleaning PLTS -- dari checklist di Google Drive

Notebook ini menjalankan `peta_progress_cleaning.py`: mengunduh
`Report & Schedule Cleaning PLTS IKN.xlsx` dari folder **raw data input** di
Drive, lalu membangun satu HTML berisi:
- peta 4.470 meja berwarna menurut hari sejak terakhir dicentang bersih,
  per tanggal (penggeser + putar ulang seluruh riwayat),
- progress per cycle (= sheet checklist) terhadap jadwalnya,
- linimasa jadwal vs hari kerja, dan rincian per tanggal.

Kode diambil dari **GitHub**, bukan dari salinan Drive, jadi perubahan yang
belum di-push tidak ikut. Folder Drive harus bisa dibuka "siapa saja yang
memiliki link" -- syarat yang sama dengan notebook
`Specific_Yield_Cleaning_Impact`.

Jalankan Cell 1 sampai Cell 5 berurutan. Edit hanya nilai di Cell 2.
HTML hasilnya berdiri sendiri: buka di browser mana pun, tanpa Colab.
'''

CODE_SETUP = '''# Cell 1 - Siapkan repo dari GitHub
from pathlib import Path
import os, subprocess, sys, tempfile

REPO_URL = "https://github.com/nabilhaidr/PVStringHeatmapCheck.git"

try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False
    print("Bukan Colab -- pakai repo lokal.")

def find_repo_root(start=None):
    path = Path(start or os.getcwd()).resolve()
    for candidate in [path, *path.parents]:
        if (candidate / "pv_pipeline").is_dir() and (candidate / "config").is_dir():
            return candidate
    raise RuntimeError("Repo root tidak ditemukan.")

if IN_COLAB:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                           "--upgrade", "gdown>=6.0.0"])
    # KODE dari GitHub, BUKAN dari salinan Drive: salinan Drive bisa tertinggal
    # sementara .git-nya melaporkan commit yang keliru. Clone dangkal menutup
    # kelas kegagalan itu. KONSEKUENSINYA: suntingan yang belum dipush TIDAK ikut.
    REPO_DIR = Path("/content/PVStringHeatmapCheck")
    if (REPO_DIR / ".git").is_dir():
        subprocess.check_call(["git", "-C", str(REPO_DIR),
                               "fetch", "--depth", "1", "origin", "master"])
        subprocess.check_call(["git", "-C", str(REPO_DIR),
                               "reset", "--hard", "origin/master"])
    else:
        subprocess.check_call(["git", "clone", "--depth", "1",
                               REPO_URL, str(REPO_DIR)])
else:
    REPO_DIR = find_repo_root()

os.chdir(REPO_DIR)
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))
INPUT_DIR = Path(tempfile.mkdtemp(prefix="peta_cleaning_inputs_"))

_v = subprocess.run(["git", "-C", str(REPO_DIR), "log", "--oneline", "-1"],
                    capture_output=True, text=True)
print("versi repo:", (_v.stdout.strip() or _v.stderr.strip()
                      or "(bukan git repo -- salinan manual?)"))
print("KODE :", REPO_DIR)

# Penanda ISI: nama yang dipanggil sel di bawah harus ada di modulnya, supaya
# repo yang tertinggal gagal DI SINI, bukan di tengah Cell 4. Sebuah tes
# menjaga daftar ini tetap lengkap.
_WAJIB = ("main",)
import peta_progress_cleaning as _ppc
_hilang = [n for n in _WAJIB if not hasattr(_ppc, n)]
if _hilang:
    raise RuntimeError(
        f"Repo TERTINGGAL: peta_progress_cleaning.py tidak punya {_hilang}. "
        f"Jalankan ulang dari Cell 1."
    )
print(f"versi repo (isi): peta_progress_cleaning lengkap ({len(_WAJIB)} nama)")
'''

CODE_CONFIG = '''# Cell 2 - Konfigurasi input (edit nilai di sini)
import re
from pv_pipeline.yf_ratio_report import validate_drive_folder_url

# Folder Drive: Cek PV String/raw data input. Alamat dari bilah browser boleh
# ditempel apa adanya: segmen "/u/2/" (nomor akun Google yang sedang login di
# browser itu) dibuang di bawah, karena validator hanya menerima
# /drive/folders/<id>.
URL_RAW_INPUT = "https://drive.google.com/drive/u/2/folders/1y37AsVViI7IL1tCRhvAGEjiq9wWnfu_e"
CLEANING_REPORT_FILENAME = "Report & Schedule Cleaning PLTS IKN.xlsx"

URL_RAW_INPUT = re.sub(r"/drive/u/\\d+/", "/drive/", URL_RAW_INPUT)
validate_drive_folder_url(URL_RAW_INPUT)
print("Raw data input:", URL_RAW_INPUT)
print("Checklist     :", CLEANING_REPORT_FILENAME)
'''

CODE_DOWNLOAD = '''# Cell 3 - Unduh checklist dari Drive
from pv_pipeline.yf_ratio_report import download_drive_file
if any(name not in globals() for name in ("URL_RAW_INPUT", "INPUT_DIR")):
    raise RuntimeError("Jalankan Cell 1 dan Cell 2 terlebih dahulu.")

CHECKLIST_XLSX = download_drive_file(
    URL_RAW_INPUT, INPUT_DIR, basename=CLEANING_REPORT_FILENAME,
)
print(f"Checklist: {CHECKLIST_XLSX.name} "
      f"({CHECKLIST_XLSX.stat().st_size / 1024:,.0f} KB)")
'''

CODE_BUILD = '''# Cell 4 - Bangun peta
import pandas as pd
from peta_progress_cleaning import main
if "CHECKLIST_XLSX" not in globals():
    raise RuntimeError("Jalankan Cell 3 terlebih dahulu.")

# Nama berkas memakai tanggal WITA supaya versi lama tidak tertimpa saat diunduh.
_hari = pd.Timestamp.now(tz="Asia/Makassar").strftime("%Y%m%d")
OUTPUT_HTML = REPO_DIR / "output_string" / f"Peta_Progress_Cleaning_PLTS_{_hari}.html"
main([str(CHECKLIST_XLSX), "--keluaran", str(OUTPUT_HTML)])
'''

CODE_DOWNLOAD_HTML = '''# Cell 5 - Download HTML dari Colab; lokal hanya menampilkan path
if "OUTPUT_HTML" not in globals() or not OUTPUT_HTML.exists():
    raise RuntimeError("Jalankan Cell 4 terlebih dahulu.")
try:
    from google.colab import files
except ImportError:
    print("Bukan Colab; HTML tersedia di", OUTPUT_HTML)
else:
    files.download(str(OUTPUT_HTML))
'''

CELLS = [
    ("markdown", MD_INTRO),
    ("code", CODE_SETUP),
    ("code", CODE_CONFIG),
    ("code", CODE_DOWNLOAD),
    ("code", CODE_BUILD),
    ("code", CODE_DOWNLOAD_HTML),
]


def _cell(kind: str, source: str, index: int) -> dict:
    cell = {
        "cell_type": kind,
        "id": f"peta-cleaning-{index:02d}",
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }
    if kind == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def build(out: Path = OUT) -> Path:
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = {
        "cells": [
            _cell(kind, source, index)
            for index, (kind, source) in enumerate(CELLS)
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    target.write_text(
        json.dumps(notebook, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {target} ({len(CELLS)} cells)")
    return target


if __name__ == "__main__":
    build()
