"""Kısa vadeli faiz (Dalga 3): OECD aylık 3 aylık bankalar arası faiz (IR3TIB), yüzde/yıl.

Neden OECD (2026-09-28): FRED `fredgraph.csv` bu ağdan bağlantı kurup veri göndermiyor (bot koruması); OECD SDMX
servisi yedi ülkeyi (ABD dahil) 2010'dan tek dosyada, anahtarsız veriyor. Tek kaynak: taşıma farkı tutarlı.

Point-in-time (kural 9): ay ortalaması ay bitince yayımlanır, OECD bir-iki ay gecikir. Bir günün faizi olarak
`GECIKME_AY` önceki ayın değeri kullanılır (varsayılan 2): o gün kesinlikle yayımlanmış olan değer. Eksik aylar önceki
değerle doldurulur (ör. İngiltere 2026-02'den sonra yok).
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import UTC, datetime

import numpy as np

URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,/{ulkeler}.M.IR3TIB.PA.....?"
       "startPeriod=2009-01&dimensionAtObservation=AllDimensions&format=csvfilewithlabels")
ULKELER = ("USA", "EA20", "GBR", "JPN", "CHE", "CAN", "AUS")
PARA = {"USD": "USA", "EUR": "EA20", "GBP": "GBR", "JPY": "JPN", "CHF": "CHE", "CAD": "CAN", "AUD": "AUS"}
GECIKME_AY = 2


def indir(ham, http_al) -> tuple[bytes, bool]:
    """Ham CSV'yi indirir ve ham depoya yazar (hash kimliği). `http_al(url) -> bytes`. Dönüş: (içerik, yeni_mi)."""
    icerik = http_al(URL.format(ulkeler="+".join(ULKELER)))
    _, _, yeni = ham.kaydet("oecd", "IR3TIB/aylik", icerik, "csv")
    return icerik, yeni


def coz(icerik: bytes) -> dict[str, dict[tuple[int, int], float]]:
    """CSV → {ülke: {(yıl, ay): oran (ondalık, ör. 0,0382)}}."""
    out: dict[str, dict[tuple[int, int], float]] = defaultdict(dict)
    for r in csv.DictReader(io.StringIO(icerik.decode("utf-8-sig"))):
        if r.get("MEASURE") != "IR3TIB" or not r.get("OBS_VALUE"):
            continue
        y, a = map(int, r["TIME_PERIOD"].split("-"))
        out[r["REF_AREA"]][(y, a)] = float(r["OBS_VALUE"]) / 100
    return dict(out)


def gunluk(aylik: dict[tuple[int, int], float], gunler_ms: np.ndarray, gecikme_ay: int = GECIKME_AY) -> np.ndarray:
    """Her gün için o gün bilinen faiz: `gecikme_ay` önceki ayın değeri; yoksa daha eskisi (ileri doldurma). Hiç
    değer yoksa NaN."""
    if not aylik:
        return np.full(len(gunler_ms), np.nan)
    sirali = sorted(aylik)
    anahtar = np.array([y * 12 + (a - 1) for y, a in sirali])
    deger = np.array([aylik[k] for k in sirali])
    out = np.full(len(gunler_ms), np.nan)
    for i, t in enumerate(gunler_ms):
        d = datetime.fromtimestamp(int(t) / 1000, UTC)
        hedef = d.year * 12 + (d.month - 1) - gecikme_ay
        j = np.searchsorted(anahtar, hedef, side="right") - 1
        if j >= 0:
            out[i] = deger[j]
    return out
