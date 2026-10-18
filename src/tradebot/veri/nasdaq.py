"""Nasdaq evreni: Nasdaq-100'ün bugüne kadarki bütün üyeleri (point-in-time üyelik `nasdaq100`), Yahoo günlük barları.

Kimlik `NASDAQ:<bugünkü Yahoo sembolü>` (eşlenen semboller tek kimlikte birleşir: FB ve META → NASDAQ:META). Sembolde
nokta Yahoo'da tire olur. Yahoo'da verisi olmayan tarihî üyeler kayda `veri_yok` olarak girer: evren yanlılığı
kalite raporunda görünür kalır (gizlenmez).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from tradebot.ayar import Ayarlar
from tradebot.kayit import log
from tradebot.veri import enstruman as en
from tradebot.veri import nasdaq100 as nq
from tradebot.veri.depo import HamDepo
from tradebot.veri.http import YokHatasi
from tradebot.veri.yahoo import Yahoo

PIYASA = "NASDAQ"
_log = log("veri.nasdaq")


@dataclass(frozen=True)
class Uyelik:
    donem: dict[str, list[tuple[int, int | None]]]   # kimlik → [(baş, bit|None)]
    kaynak_sha: str                                   # yıllık ham dosyaların birleşik kimliği (veri hash'ine girer)

    def kimlikler(self) -> list[str]:
        return sorted(self.donem)

    def uyeler(self, an_ms: int) -> list[str]:
        """`an_ms` günü üye olan kimlikler."""
        return sorted(k for k, v in self.donem.items() if any(b <= an_ms and (e is None or an_ms < e) for b, e in v))


def enstrumanlar(evren: dict, kimlikler: list[str]) -> list[en.Enstruman]:
    b = evren["nasdaq"]
    out = []
    for k in kimlikler:
        s = k.removeprefix(f"{PIYASA}:")
        out.append(en.Enstruman(b["piyasa"], s, b["sinif"], b["takvim"], b["para_birimi"], "yahoo",
                                {"kaynak_sembol": s.replace(".", "-"),
                                 "evren_uyarisi": "Nasdaq-100 tarihî üyesi; evren üyelik dönemiyle (PIT) kısıtlı"}))
    return out


TURETILMIS = "nasdaq/uyelik.json"   # veri dizininde; hamdan yeniden üretilir (araştırma ve düğüm motor açmadan okur)


def uyelik_yaz(veri_dizini, uy: Uyelik, commit: str) -> None:
    import json
    import os
    from pathlib import Path

    yol = Path(veri_dizini) / TURETILMIS
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".yaziliyor")
    gecici.write_text(json.dumps({"commit": commit, "kaynak_sha": uy.kaynak_sha,
                                  "donem": {k: [list(x) for x in v] for k, v in sorted(uy.donem.items())}}),
                      encoding="utf-8")
    os.replace(gecici, yol)


def uyelik_dosyadan(veri_dizini) -> Uyelik:
    import json
    from pathlib import Path

    yol = Path(veri_dizini) / TURETILMIS
    if not yol.exists():
        raise FileNotFoundError(f"{yol} yok: önce `tradebot veri nasdaq`")
    d = json.loads(yol.read_text(encoding="utf-8"))
    return Uyelik({k: [(int(b), None if e is None else int(e)) for b, e in v] for k, v in d["donem"].items()},
                  d["kaynak_sha"])


def uyelik_yukle(ham: HamDepo, ayar: dict | None = None, indir: bool = False, http=None) -> Uyelik:
    """Ham depodaki sabit commit dosyalarından üyelik (`indir`: önce kaynaktan çek; aynı içerik yeniden yazılmaz)."""
    import hashlib

    ayar = ayar or nq.ayar_oku()
    yillar = nq.indir(ham, ayar, http) if indir else nq.yerel(ham, ayar)
    if not yillar:
        raise FileNotFoundError("Nasdaq-100 üyelik dosyası yok: önce `tradebot veri nasdaq`")
    sha = hashlib.sha256(b"|".join(hashlib.sha256(yillar[y]).digest() for y in sorted(yillar))).hexdigest()
    return Uyelik(nq.kimlik_donemleri(nq.donemler(yillar), ayar, PIYASA), sha)


def guncelle(a: Ayarlar, m: Engine, tam: bool = False, yalniz_guncel: bool = False) -> dict:
    """Üyeliği indirir, bütün tarihî üyeleri kaydeder ve Yahoo günlük barlarını günceller. `yalniz_guncel`: yalnız
    bugünkü üyeler (canlı düğümün hızlı yolu)."""
    ham = HamDepo(a.veri_dizini, m)
    ayar = nq.ayar_oku()
    uy = uyelik_yukle(ham, ayar, indir=True)
    uyelik_yaz(a.veri_dizini, uy, ayar["uyelik"]["commit"])
    y = Yahoo(a.veri_dizini, m)
    kimlikler = uy.uyeler(int(time.time() * 1000)) if yalniz_guncel else uy.kimlikler()
    liste = enstrumanlar(y.evren, kimlikler)
    en.kaydet(m, liste)
    bas = y.evren["nasdaq"]["baslangic"]
    sonuc, yok, hata = [], [], []
    for e in liste:
        try:
            r = y.gunluk(e, bas, tam=tam)
        except YokHatasi:
            en.sinir_guncelle(m, e.kimlik, None, None, "veri_yok")
            yok.append(e.sembol)
            continue
        except Exception as ex:  # noqa: BLE001 — bir sembol diğerlerini durdurmaz
            hata.append(e.sembol)
            _log.error("nasdaq_sembol_hatasi", kimlik=e.kimlik, hata=f"{type(ex).__name__}: {ex}"[:200])
            continue
        en.sinir_guncelle(m, e.kimlik, r["ilk_ms"], r["son_ms"], "aktif")
        sonuc.append(r)
    return {"uye_kimlik": len(uy.donem), "guncellenen": len(sonuc), "veri_yok": len(yok), "hata": hata[:20],
            "tam_yenileme": sum(r["tam"] for r in sonuc), "uyelik_sha": uy.kaynak_sha[:16]}
