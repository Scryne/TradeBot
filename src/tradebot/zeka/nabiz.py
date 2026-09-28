"""Zekâ servisinin nabzı (risk katmanı 5, "habere kör" mod): servis her tur sonunda paylaşılan veri diskine yazar,
paper düğümü karar anında okur. Veritabanı yerine dosya: servisler zaten `veri` biriminini paylaşıyor, tablo göçü
gerekmez, yazım atomik (geçici dosya + yeniden adlandırma).

Kör sayılır (Final Doküman: "Jev yoksa habere kör mod, yeni giriş yarım boyut"): nabız yok ya da `ESIK_MS`'den eski
(servis çökmüş/donmuş), A1'in kaynağı Binance duyuruları `ESIK_MS`'dir çekilemiyor ya da son Jev çağrısı hatayla bitti.
Belirsizlikte kör: dosya okunamıyorsa kör (kural 8: belirsiz durumda riski azalt).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ESIK_MS = 15 * 60_000
DOSYA = "nabiz/zeka.json"
A1_KAYNAGI = "binance_duyuru"


def yaz(veri_dizini: Path, simdi_ms: int, basarili_kaynaklar: set[str], jev_son_basari_ms: int | None,
        jev_son_hata_ms: int | None) -> dict:
    """Önceki nabzı okuyup başarılı kaynakların zamanını tazeler (başarısızınki eski kalır) ve yazar."""
    yol = Path(veri_dizini) / DOSYA
    onceki = oku(veri_dizini) or {}
    son = dict(onceki.get("son_basari") or {})
    for k in basarili_kaynaklar:
        son[k] = simdi_ms
    n = {"zaman_ms": simdi_ms, "son_basari": son, "jev_son_basari_ms": jev_son_basari_ms,
         "jev_son_hata_ms": jev_son_hata_ms}
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".yaziliyor")
    gecici.write_text(json.dumps(n), encoding="utf-8")
    os.replace(gecici, yol)
    return n


def oku(veri_dizini: Path) -> dict | None:
    try:
        return json.loads((Path(veri_dizini) / DOSYA).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def kor_mu(veri_dizini: Path, simdi_ms: int, esik_ms: int = ESIK_MS) -> tuple[bool, str]:
    """(kör mü, neden)."""
    n = oku(veri_dizini)
    if n is None:
        return True, "nabız yok"
    if simdi_ms - int(n.get("zaman_ms") or 0) > esik_ms:
        return True, "zekâ servisi tur atmıyor"
    if simdi_ms - int((n.get("son_basari") or {}).get(A1_KAYNAGI) or 0) > esik_ms:
        return True, "Binance duyuruları çekilemiyor"
    hata, basari = n.get("jev_son_hata_ms"), n.get("jev_son_basari_ms")
    if hata is not None and hata > (basari or 0):
        return True, "son Jev çağrısı hatalı"
    return False, ""
