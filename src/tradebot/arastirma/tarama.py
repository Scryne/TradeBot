"""Parametre taraması: ızgaradaki her kombinasyon → sinyal → backtest → metrik → deneme defteri; ardından
en iyisi için DSR (ailenin toplam deneme sayısıyla), plato, walk-forward ve yıllık kırılım.

Bar yükleme: istenen zaman dilimi depoda yoksa temel zaman diliminden türetilir (kripto günlük = 00:00 UTC kovası).
Veri kimliği: kullanılan bar dosyasının SHA-256'sı (deneme kaydında).
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np

from tradebot.arastirma import dogrulama as dg
from tradebot.arastirma import metrik as mt
from tradebot.arastirma.backtest import calistir
from tradebot.arastirma.defter import Defter
from tradebot.arastirma.maliyet import model
from tradebot.cekirdek import Barlar, StratejiTanimi, nedensellik_testi, ornek
from tradebot.veri.depo import BarDepo, turet
from tradebot.veri.takvim import ZAMAN_DILIMI_MS

STRATEJILER = {
    "sma_kesisim": ("trend", ornek.sma_kesisim),
    "donchian": ("kirilim", ornek.donchian),
    "tsmom": ("trend", ornek.tsmom),
}
YIL_MS = int(365.25 * 86_400_000)


def bar_yukle(depo: BarDepo, kimlik: str, zd: str) -> tuple[Barlar, np.ndarray | None, str]:
    """(barlar, yarım spread bps ya da None, veri hash'i)."""
    for kaynak_zd in ([zd] + [z for z in ("1h", "1m") if ZAMAN_DILIMI_MS[z] < ZAMAN_DILIMI_MS[zd]]):
        yol = depo.yol(kimlik, kaynak_zd)
        if yol.exists():
            df = depo.oku(kimlik, kaynak_zd)
            if kaynak_zd != zd:
                df = turet(df, ZAMAN_DILIMI_MS[zd]).sort("acilis_ms")
            h = hashlib.sha256(Path(yol).read_bytes()).hexdigest()
            ys = (df["spread"].to_numpy() / 2 / df["open"].to_numpy() * 1e4) if "spread" in df.columns else None
            b = Barlar.sozlukten({k: df[c] for k, c in (("t", "acilis_ms"), ("open", "open"), ("high", "high"),
                                                           ("low", "low"), ("close", "close"), ("volume", "volume"))})
            return b, ys, h
    raise FileNotFoundError(f"{kimlik} için {zd} ya da türetilebilir bar yok")


def tara(defter: Defter, depo: BarDepo, plan: str, strateji: str, kimlik: str, piyasa: str, sinif: str, zd: str,
         izgara: dict, yon: str = "long", bant: float = 0.0, is_yil: float = 3.0, oos_yil: float = 1.0,
         izin_kirli: bool = False) -> dict:
    aile, fonk = STRATEJILER[strateji]
    b, ys, veri_hash = bar_yukle(depo, kimlik, zd)
    mm = model(piyasa, sinif)
    kosular, puanlar, satirlar = {}, {}, []
    for p in dg.izgara(izgara):
        tanim = StratejiTanimi(strateji, aile, fonk, p, yon=yon)
        nedensellik_testi(tanim, b, deneme=5)  # her kombinasyon geleceği görmediğini kanıtlamadan kaydedilmez
        t0 = time.perf_counter()
        s = calistir(b.t, b.open, tanim.sinyal(b), mm, yari_spread_bps=ys, bant=bant)
        m = mt.hesapla(s)
        hs = np.expm1(mt.haftalik_log(s.t, s.net))
        sr_h = float(hs.mean() / hs.std(ddof=1)) if len(hs) > 1 and hs.std(ddof=1) > 0 else 0.0
        kayit = m.sozluk() | {"sharpe_haftalik": sr_h}
        defter.kaydet(plan, "tarama", tanim.kimlik(), aile, p, kimlik, zd, veri_hash, kayit, time.perf_counter() - t0,
                      izin_kirli=izin_kirli)
        kosular[tanim.kimlik()] = {"net": s.net, "pozisyon": s.pozisyon, "t": s.t}
        puanlar[tanim.kimlik()] = m.puan
        satirlar.append({"strateji": tanim.kimlik(), **kayit})
    en_iyi = max(satirlar, key=lambda r: r["puan"])
    kimlik_f = lambda p: StratejiTanimi(strateji, aile, fonk, p, yon=yon).kimlik()  # noqa: E731
    en_iyi_kos = kosular[en_iyi["strateji"]]
    aile_sr = [float(x) for x in _aile_haftalik_sr(defter, aile)]
    dsr = dg.haftalik_dsr(en_iyi_kos["t"], en_iyi_kos["net"], defter.deneme_sayisi(aile), aile_sr)
    t_ortak = next(iter(kosular.values()))["t"]
    wf = dg.walk_forward(t_ortak, kosular, int(is_yil * YIL_MS), int(oos_yil * YIL_MS),
                         puan=lambda t, n: float(np.mean(mt.haftalik_log(t, n))) if len(n) else -1.0,
                         taraf_maliyet=mm.taraf_bps() / 1e4)
    wf_ozet = {"pencere": wf.get("pencere", 0), "farkli_secim": wf.get("farkli_secim", 0)}
    if wf.get("pencere"):
        from tradebot.arastirma.backtest import Sonuc
        wf_s = Sonuc(wf["t"], np.zeros(len(wf["net"])), wf["net"], np.zeros(len(wf["net"])), wf["net"],
                     np.zeros(len(wf["net"])), wf["ozkaynak"])
        wm = mt.hesapla(wf_s)
        wf_ozet |= {"oos_puan": wm.puan, "oos_yillik": wm.yillik_bilesik, "oos_en_kotu_dusus": wm.en_kotu_dusus,
                    "oos_en_kotu_hafta": wm.en_kotu_hafta, "oos_sharpe": wm.sharpe,
                    "secimler": [s["secilen"] for s in wf["secimler"]]}
    al_tut = calistir(b.t, b.open, np.ones(len(b)), mm, yari_spread_bps=ys, bant=1.0)
    return {
        "plan": plan, "enstruman": kimlik, "zd": zd, "bar": len(b), "veri_hash": veri_hash[:12], "maliyet": mm.ad,
        "kombinasyon": len(satirlar), "satirlar": sorted(satirlar, key=lambda r: -r["puan"]),
        "en_iyi": en_iyi, "dsr": dsr, "plato": dg.plato(izgara, puanlar, kimlik_f), "walk_forward": wf_ozet,
        "yillik": dg.yillik_kirilim(en_iyi_kos["t"], en_iyi_kos["net"]),
        "al_tut": mt.hesapla(al_tut).sozluk(),
    }


def _aile_haftalik_sr(defter: Defter, aile: str) -> list[float]:
    from sqlalchemy import select

    from tradebot.db import deneme

    with defter.motor.connect() as b:
        return [m.get("sharpe_haftalik", 0.0) for m in
                b.execute(select(deneme.c.metrik).where(deneme.c.aile == aile, deneme.c.tur == "tarama")).scalars()]
