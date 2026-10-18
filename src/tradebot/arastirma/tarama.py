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
from tradebot.cekirdek.boyut import kaldirac_dogrula, oynaklik_hedefi, yarim_kelly_tavani
from tradebot.risk.motor import PortfoyIzleyici, RiskAyar
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


def bar_yil(zd: str, takvim_adi: str) -> float:
    """Yılda bar sayısı (oynaklık yıllıklandırma): 7/24 takvim süre, borsa ~252 seans, FX ~260 gün."""
    if takvim_adi == "kripto_7x24":
        return 365.25 * 86_400_000 / ZAMAN_DILIMI_MS[zd]
    if takvim_adi == "fx_24x5":
        return 260.0 * max(1.0, 86_400_000 / ZAMAN_DILIMI_MS[zd])
    # borsa: gün içi barlar yalnız seansta (~6,5 saat), 24 saat değil
    return 252.0 * max(1.0, 6.5 * 3_600_000 / ZAMAN_DILIMI_MS[zd]) if zd != "1d" else 252.0


def tara(defter: Defter, depo: BarDepo, plan: str, strateji: str, kimlik: str, piyasa: str, sinif: str, zd: str,
         izgara: dict, yon: str = "long", bant: float = 0.0, is_yil: float = 3.0, oos_yil: float = 1.0,
         izin_kirli: bool = False, hedef_vol: float | None = None, kaldirac: float = 1.0, vol_pencere: int = 30,
         frenler: bool = False, takvim_adi: str = "kripto_7x24") -> dict:
    aile, ham_fonk = STRATEJILER[strateji]
    kaldirac = kaldirac_dogrula(kaldirac)
    b, ys, veri_hash = bar_yukle(depo, kimlik, zd)
    mm = model(piyasa, sinif)
    by = bar_yil(zd, takvim_adi)
    boyut = {"hedef_vol": hedef_vol, "kaldirac": kaldirac, "vol_pencere": vol_pencere} if hedef_vol else {}

    def fonk(bb, **p):
        s = ham_fonk(bb, **{k: v for k, v in p.items() if k not in ("hedef_vol", "kaldirac", "vol_pencere")})
        return oynaklik_hedefi(s, bb.close, hedef_vol, by, vol_pencere, azami=kaldirac) if hedef_vol else s

    def izleyici():
        # Araştırma modu: acil durdurma olay + kapı koşulu, kalıcı değil (Faz 4 kararı; canlıda kalıcı)
        return PortfoyIzleyici(RiskAyar(kaldirac=kaldirac), baslangic_ms=int(b.t[0]), acil_kalici=False) if frenler else None
    kosular, puanlar, satirlar = {}, {}, []
    for p0 in dg.izgara(izgara):
        p = p0 | boyut
        tanim = StratejiTanimi(strateji, aile, fonk, p, yon=yon)
        nedensellik_testi(tanim, b, deneme=5)  # her kombinasyon geleceği görmediğini kanıtlamadan kaydedilmez
        t0 = time.perf_counter()
        s = calistir(b.t, b.open, tanim.sinyal(b), mm, yari_spread_bps=ys, bant=bant, izleyici=izleyici())
        m = mt.hesapla(s)
        hs = np.expm1(mt.haftalik_log(s.t, s.net))
        sr_h = float(hs.mean() / hs.std(ddof=1)) if len(hs) > 1 and hs.std(ddof=1) > 0 else 0.0
        durum = s.durum if s.durum is not None else np.zeros(0)
        acil = int((durum == 3).sum())
        kayit = m.sozluk() | {"sharpe_haftalik": sr_h, "fren_bar": int((durum > 0).sum()), "acil_durdurma": acil > 0,
                              "acil_sayisi": acil, "yarim_kelly": yarim_kelly_tavani(hs)}
        kayit["kapilar_gecti"] = bool(kayit["kapilar_gecti"] and acil == 0)  # acil tetikleyen strateji geçemez
        defter.kaydet(plan, "tarama", tanim.kimlik(), aile, p, kimlik, zd, veri_hash, kayit, time.perf_counter() - t0,
                      izin_kirli=izin_kirli)
        kosular[tanim.kimlik()] = {"net": s.net, "pozisyon": s.pozisyon, "t": s.t}
        puanlar[tanim.kimlik()] = m.puan
        satirlar.append({"strateji": tanim.kimlik(), "_p0": p0, **kayit})
    en_iyi = max(satirlar, key=lambda r: r["puan"])
    kimlik_f = lambda p: StratejiTanimi(strateji, aile, fonk, p | boyut, yon=yon).kimlik()  # noqa: E731
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
        "boyut": boyut or "yok (ya hep ya hiç)", "frenler": frenler,
        "kombinasyon": len(satirlar), "satirlar": sorted(({k: v for k, v in r.items() if k != "_p0"} for r in satirlar),
                                                      key=lambda r: -r["puan"]),
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
