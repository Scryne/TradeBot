"""Pano için sentetik örnek veri (yalnız yerel geliştirme ve test): canlı defterle aynı şekil, uydurma sayılar.

Canlı veritabanına ASLA yazılmaz: yalnız SQLite adresi kabul edilir.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine, insert
from sqlalchemy.engine import Engine

from tradebot.db import (
    deneme,
    jev_yargi,
    metadata,
    olay,
    paper_dagitim,
    paper_emir,
    paper_emir_olay,
    paper_karar,
    paper_kol,
    paper_ozkaynak,
    test_plani,
)
from tradebot.pano.veri import kol_bilgi

SAAT = 3_600_000
KAYNAKLAR = ["ma_yon@kripto_btc_eth@1h", "tsmom@kripto_btc_eth@4h", "d2:donchian_ls@kripto_btc_eth@4h",
             "d2:donchian_ls@kripto_btc_eth@1d", "d2:tsmom@kripto_btc_eth@4h"]
BTC, ETH = "BINANCE:BTCUSDT", "BINANCE:ETHUSDT"


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC)


def kur(url: str, simdi_ms: int, gun: int = 16, veri_dizini: Path | None = None, tohum: int = 7) -> Engine:
    if not url.startswith("sqlite"):
        raise ValueError("örnek veri yalnız SQLite'a yazılır")
    m = create_engine(url, future=True)
    metadata.drop_all(m)
    metadata.create_all(m)
    rng = np.random.default_rng(tohum)
    son = simdi_ms // SAAT * SAAT
    bas = son - gun * 24 * SAAT
    t = np.arange(bas, son + SAAT, SAAT)
    n = len(t)
    # BTC/ETH: hafif yukarı eğilimli, ortada sert bir düşüş (fren ve veto görünsün)
    g = rng.normal(0.0, 0.0045, (n, 2))
    g[: int(n * 0.45)] += np.array([0.0006, 0.0008])          # yükseliş: trend kolları uzun
    g[n // 2: n // 2 + 10] += np.array([-0.009, -0.013])     # çöküş: fren ve veto
    g[int(n * 0.7):] += np.array([0.0004, 0.0003])           # toparlanma
    fiyat = np.exp(np.cumsum(g, axis=0)) * np.array([81_500.0, 2_610.0])
    kollar = [k for b in KAYNAKLAR for k in (b, b + "+jev")] + ["agresif@kripto_btc_eth", "portfoy@kripto_btc_eth"]
    siniflar = {k: "B" for k in kollar} | {"agresif@kripto_btc_eth": "gozlem", "portfoy@kripto_btc_eth": "portfoy"}
    veto_saat = {int(t[n // 2 + 2]), int(t[n // 2 + 3]), int(t[n - 30])}
    with m.begin() as b:
        for k in kollar:
            b.execute(insert(paper_kol).values(kol=k, acilis=_dt(bas), baslangic_ms=bas, baslangic_ozkaynak=100_000.0,
                                               sinif=siniflar[k], tanim={"strateji": k.split("@")[0]}, kod_surumu="ornek"))
        emir_id = 0
        for j, k in enumerate(kollar):
            adim = {"1h": 1, "4h": 4, "1d": 24}.get(kol_bilgi(k)["zd"], 1)
            ufuk = 24 * (3 + j % 5)
            oz, nakit, poz = 100_000.0, 100_000.0, np.zeros(2)
            hedef = np.zeros(2)
            for i in range(n):
                p = fiyat[i]
                oz = nakit + float(poz @ p)
                durum = "normal"
                if n // 2 + 4 <= i <= n // 2 + 20 and j % 3 == 0:
                    durum = "fren_gunluk"
                karar_var = i % adim == 0 and i > ufuk // 4
                vetolu = k.endswith("+jev") and int(t[i]) in veto_saat
                if karar_var and not k.startswith("portfoy"):
                    mom = np.log(fiyat[i] / fiyat[max(0, i - ufuk)])
                    hedef = np.where(mom > 0, 0.22 + 0.08 * (j % 4), 0.0)
                    if k.startswith("agresif"):
                        hedef = np.where(mom > 0, 0.5, 0.0)
                    if durum != "normal":
                        hedef = np.minimum(hedef, np.abs(poz * p) / max(oz, 1))
                    if vetolu:
                        hedef = hedef * 0.0
                    yeni = hedef * oz / p
                    fark = yeni - poz
                    kid = b.execute(insert(paper_karar).values(
                        kol=k, bar_ms=int(t[i]) - SAAT, karar_ms=int(t[i]) + 4_000, kod_surumu="ornek", veri_hash="0" * 64,
                        durum=durum, ayrinti={"kimlikler": [BTC, ETH], "hedef": hedef.tolist(), "yeni": hedef.tolist(),
                                              "veto": [BTC] if vetolu else [], "gecikmeli": False})).inserted_primary_key[0]
                    for e, (kim, d) in enumerate(zip((BTC, ETH), fark, strict=True)):
                        if abs(d * p[e]) < 0.02 * oz:
                            continue
                        emir_id += 1
                        b.execute(insert(paper_emir).values(
                            kol=k, karar_id=kid, istemci_emir_id=f"O-ORNEK-{emir_id}", enstruman=kim, istenen=float(d),
                            onaylanan=float(d), karar_fiyati=float(p[e]), gonderim_fiyati=float(p[e]),
                            zaman_ms=int(t[i]) + 5_000, tur="karar",
                            risk={"onay": True, "gerekceler": [], "risk_azaltan": bool(d < 0)}))
                        dolum = float(p[e]) * (1 + math.copysign(0.00025, d))
                        ucret = abs(d) * dolum * 0.001
                        b.execute(insert(paper_emir_olay).values(
                            emir_id=emir_id, kol=k, tur="dolum", enstruman=kim, miktar=float(d), fiyat=dolum, ucret=ucret,
                            zaman_ms=int(t[i]) + 5_400, ayrinti={"komisyon_para": "USDT"}))
                        nakit -= d * dolum + ucret
                        poz[e] += d
                    oz = nakit + float(poz @ p)
                b.execute(insert(paper_ozkaynak).values(
                    kol=k, zaman_ms=int(t[i]), ozkaynak=oz, nakit=nakit,
                    pozisyon={BTC: float(poz[0]), ETH: float(poz[1])} if poz.any() else {},
                    fiyat={BTC: float(p[0]), ETH: float(p[1])} if poz.any() else {}))
        b.execute(insert(paper_dagitim).values(
            portfoy="portfoy@kripto_btc_eth", hafta_ms=int(bas), hesap_ms=int(bas) + 2000, kod_surumu="ornek", kaldirac=0.0,
            ayrinti={"kollar": {k + "+jev": {"sinif": "B", "agirlik": 0.0, "katsayi": 0.0} for k in KAYNAKLAR}}))
        # Jev olayları ve yargıları
        for i in range(60):
            z = son - int(rng.integers(0, 7 * 24)) * SAAT
            tur, rol, ens = [("kurumsal", "A2_kap", "BIST:THYAO"), ("uyari", "A1_binance", "BINANCE:ICXUSDT"),
                             ("veto", "A1_binance", "BINANCE:ALPACAUSDT"), ("kurumsal", "A2_kap", "BIST:ASELS")][i % 4]
            b.execute(insert(olay).values(
                zaman=_dt(z), tur=tur, enstruman=ens, gecerli_ms=z, bitis_ms=None if tur != "uyari" else z + 7 * 24 * SAAT,
                neden={"veto": "A1 jev:delist (0.97): Binance Will Delist ALPACA on 2026-10-06",
                       "uyari": "A1 jev:izleme_etiketi (0.81): Binance adds ICX to Monitoring Tag",
                       "kurumsal": "A2 jev:kurumsal_islem (0.93): Kar payı dağıtımı"}[tur],
                rol=rol, metin_id=i, yargi_id=i, ayrinti={"guven": 0.8 + 0.19 * rng.random(), "canli": True}))
        for i in range(400):
            b.execute(insert(jev_yargi).values(
                zaman=_dt(son - int(rng.integers(0, 24 * 60)) * 60_000), rol="A1_binance",
                saglayici="nvidia" if i % 25 == 0 else "jev", model_istenen="jev", model_cozulen="jev-1.4.0",
                soru_sha="a" * 64, girdi_sha=f"{i:064d}", hedef="metin:1", cevap={}, gecikme_ms=float(rng.gamma(4, 180))))
        planlar = [("2026-09-25-d1-trend", "trend", "acik", None, 214), ("2026-09-26-d2-trend", "trend", "acik", None, 160),
                   ("2026-09-27-c1-veto-etkisi", "c1", "kapandi", "A1 VAR (7g medyan anormal −%21,1). A2 ZAYIF.", 2),
                   ("2026-09-28-viop1-trend", "trend", "acik", None, 96), ("2026-09-28-viop2-tasima", "tasima", "acik", None, 8),
                   ("2026-09-27-altin-m15", "altin", "acik", None, 192)]
        for kim, aile, durum, sonuc, adet in planlar:
            b.execute(insert(test_plani).values(kimlik=kim, zaman=_dt(bas), aile=aile, hipotez=f"{aile} hipotezi (örnek)",
                                                izgara={}, piyasalar=[], olcut="dalga ölçütü", kod_surumu="ornek",
                                                durum=durum, sonuc=sonuc))
            for _ in range(adet):
                b.execute(insert(deneme).values(zaman=_dt(bas), plan=kim, tur="tarama", strateji=aile, aile=aile,
                                                parametreler={}, enstruman="X", zaman_dilimi="1d", veri_hash="0",
                                                kod_surumu="ornek", metrik={}, sure_sn=0.1))
    if veri_dizini is not None:
        for dalga, plan, kol, karar, sh in [("dalga1", "2026-09-25-d1-trend", "tsmom@kripto_btc_eth@4h", "B", 0.92),
                                            ("dalga1", "2026-09-25-d1-trend", "ma_yon@fx@1d", "KALDI", -0.21),
                                            ("dalgaviop2", "2026-09-28-viop2-tasima", "tasima@viop_usdtry@1d", "KALDI", 0.13)]:
            d = Path(veri_dizini) / "turnuva" / dalga
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{kol.replace('@', '__')}.json").write_text(json.dumps(
                {"plan": plan, "kol": kol, "karar": karar, "en_iyi": {"sharpe": sh, "yillik_bilesik": sh / 10},
                 "dsr": {"dsr": 0.3}}), encoding="utf-8")
    return m
