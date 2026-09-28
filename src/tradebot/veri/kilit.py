"""Token kilit açılımı takvimi (Dalga 6): DefiLlama'nın herkese açık `defillama.com/unlocks` sayfası.

Neden bu kaynak (2026-09-29): DefiLlama'nın emissions API'si ücretli oldu (402), açık kaynak adaptör deposu kaldırılmış
(404). Sayfanın kendisi ücretsiz ve bütün tabloyu (370 protokol, 2021–2026 arasında 35 bin+ cliff olay) sunucu tarafında
`__NEXT_DATA__` içinde gönderiyor. Ham HTML ham depoya yazılır (hash kimliktir); tablo hamdan yeniden üretilir.

Point-in-time sınırı (Dalga-6.md): açılım takvimleri token ekonomisi belgelerinde önceden yayımlanır, ama DefiLlama
geçmiş olayları sonradan düzeltmiş olabilir. Boyut, sonradan değişen dolaşımdaki arz yerine azami arza (sabit) göre
ölçülür.
"""
from __future__ import annotations

import json
import re

import polars as pl

URL = "https://defillama.com/unlocks"


def indir(ham, http_al) -> bytes:
    icerik = http_al(URL)
    ham.kaydet("defillama", "unlocks/sayfa", icerik, "html")
    return icerik


def coz(icerik: bytes) -> pl.DataFrame:
    """Sayfa → cliff olayları: sembol, gecko, zaman_ms, kategori, token, azami_arz, oran (token / azami arz)."""
    s = icerik.decode("utf-8", errors="replace")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', s, re.S)
    if m is None:
        raise ValueError("unlocks sayfasında __NEXT_DATA__ yok (sayfa yapısı değişti)")
    satir = []
    for p in json.loads(m.group(1))["props"]["pageProps"]["data"]:
        sembol, azami = (p.get("tSymbol") or "").upper(), p.get("maxSupply")
        if not sembol or not azami:
            continue
        for e in p.get("events") or []:
            if e.get("unlockType") != "cliff" or not e.get("noOfTokens"):
                continue
            t = float(sum(e["noOfTokens"]))
            if t <= 0:
                continue
            satir.append({"sembol": sembol, "gecko": p.get("gecko_id"), "ad": p.get("name"),
                          "zaman_ms": int(e["timestamp"]) * 1000, "kategori": e.get("category") or "Uncategorized",
                          "token": t, "azami_arz": float(azami), "oran": t / float(azami)})
    return pl.DataFrame(satir)
