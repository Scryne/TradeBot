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


def kur(url: str, simdi_ms: int, gun: int = 16, veri_dizini: Path | None = None, tohum: int = 7,
        kilit: bool = False) -> Engine:
    """`kilit`: kilit kolu (paper + Demo) ve takvimi de kurulur (pano; gözetmen testleri yalnız paper düğümü ister)."""
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
        if kilit:
            _kilit(b, t, fiyat[:, 0], rng)
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
        if kilit:
            _kilit_ham(m, Path(veri_dizini), son)
    return m


# ---------------------------------------------------------------------------------------------------- kilit kolu
GUN = 24 * SAAT
KILIT = "d13:kilit_kisa@kilit_perp@1d"
KILIT_TANIM = {"zd": "1d", "strateji": "kilit_kisa", "grup": "kilit_perp", "sinif": "A",
               "parametre": {"giris": -7, "cikis": 0, "notional": 0.05, "azami_btc": 0.5, "azami_brut": 1.0},
               "grup_tanim": {"yon": "kisa_notr", "dugum": "kilit", "kimlikler": ["BINANCEF:*USDT"],
                              "olay": {"asgari_oran": 0.005, "kategoriler": ["insiders", "privateSale"]}}}
# (sembol, açılım günü (bugüne göre), giriş fiyatı, giriş → açılım token getirisi). Açılımı gelecekte olanlar açık.
KILIT_OLAY = [("MOVE", -2, 0.118, -0.061), ("CARV", -1, 0.214, 0.083), ("SEI", 2, 0.287, -0.022),
              ("STRK", 4, 0.131, 0.011)]
KILIT_TAKVIM = [("SEI", 2, 0.0106, "insiders"), ("STRK", 4, 0.0208, "privateSale"), ("ARB", 6, 0.0093, "insiders"),
                ("QUAI", 7, 0.0096, "insiders"), ("ZRO", 11, 0.0236, "insiders"), ("APR", 15, 0.1167, "privateSale"),
                ("EIGEN", 23, 0.029, "insiders")]


def _kilit(b, t: np.ndarray, btc: np.ndarray, rng) -> None:
    """Kilit kolu (paper + Demo) örneği: kapanmış ve açık olaylar, günlük kararlar, funding; Demo'da emri borsa
    düşürür (2026-10-06'da SEI'de gerçekte de oldu: −1000)."""
    gun0 = int(t[-1]) // GUN * GUN
    olaylar = [(s_, gun0 + g * GUN, gun0 + (g - 7) * GUN, px, r) for s_, g, px, r in KILIT_OLAY
               if gun0 + (g - 7) * GUN > int(t[0])]
    for kol, oz0, gercek in ((KILIT, 100_000.0, False), (KILIT + "#gercek", 1_000.0, True)):
        grup = KILIT_TANIM["grup_tanim"] | ({"dugum": "kilit_gercek", "ortam": "demo"} if gercek else {})
        b.execute(insert(paper_kol).values(kol=kol, acilis=_dt(int(t[0])), baslangic_ms=int(t[0]), baslangic_ozkaynak=oz0,
                                           sinif="A", tanim=KILIT_TANIM | {"grup_tanim": grup}, kod_surumu="ornek"))
        dolum: list[tuple[int, str, float, float, dict]] = []
        ac: dict[int, list[dict]] = {}
        kapat: dict[int, list[dict]] = {}
        for s_, olay_ms, giris, px, getiri in olaylar:
            perp = f"BINANCEF:{s_}USDT"
            poz = {"sembol": s_, "olay_ms": olay_ms, "giris_ms": giris, "cikis_ms": olay_ms, "notional": 0.05}
            ac.setdefault(giris, []).append(poz)
            if gercek and s_ == "SEI":
                continue
            ortak = {"sembol": s_, "olay_ms": olay_ms, "gun_ms": giris, "cikis_ms": olay_ms, "notional": 0.05}
            i = int(np.searchsorted(t, giris + SAAT))
            q = -round(0.05 * oz0 / px)
            dolum.append((int(t[i]), perp, q, px, ortak | {"bacak": "token", "islem": "ac", "perp": perp}))
            if not gercek:
                dolum.append((int(t[i]), "BINANCEF:BTCUSDT", -q * px / btc[i], float(btc[i]),
                              ortak | {"bacak": "btc", "islem": "ac", "perp": None}))
            if olay_ms <= gun0:
                j = int(np.searchsorted(t, olay_ms + SAAT))
                kapat.setdefault(olay_ms, []).append(poz | {"neden": "cikis"})
                dolum.append((int(t[j]), perp, -q, px * (1 + getiri),
                              ortak | {"bacak": "token", "islem": "kapat", "neden": "cikis", "perp": perp}))
                if not gercek:
                    dolum.append((int(t[j]), "BINANCEF:BTCUSDT", q * px / btc[i], float(btc[j]),
                                  ortak | {"bacak": "btc", "islem": "kapat", "neden": "cikis", "perp": None}))
        for g in range(int(t[0]) // GUN * GUN + GUN, gun0 + 1, GUN):
            b.execute(insert(paper_karar).values(
                kol=kol, bar_ms=g, karar_ms=g + 5 * 60_000 + 3_000, kod_surumu="ornek", veri_hash="d" * 64, durum="normal",
                ayrinti={"tur": "kilit_kisa", "olay_sayisi": 38 + g // GUN % 3, "ac": ac.get(g, []),
                         "kapat": kapat.get(g, []), "takvim_hatasi": None, "gecikmeli": False,
                         "red": [{"sembol": "PEAQ", "olay_ms": g + 7 * GUN, "oran": 0.0145, "neden": "islem_gormuyor"}]
                         if g == gun0 else []}))
        for giris in [o[2] for o in olaylar if gercek and o[0] == "SEI"]:
            b.execute(insert(paper_emir_olay).values(
                emir_id=0, kol=kol, tur="ret", enstruman="BINANCEF:SEIUSDT", miktar=-174.0, fiyat=None, ucret=0.0,
                zaman_ms=giris + 5 * 60_000 + 9_000,
                ayrinti={"gerekceler": ["hata: BorsaHatasi: -1000: An unknown error occurred while processing the request."]}))
        dolum.sort(key=lambda x: x[0])
        for z, kim, q, p, ay in dolum:
            b.execute(insert(paper_emir_olay).values(emir_id=0, kol=kol, tur="dolum", enstruman=kim, miktar=q, fiyat=p,
                                                     ucret=abs(q * p) * 0.0005, zaman_ms=z, ayrinti=ay))
        # Saatlik işaret; token fiyatı girişten açılıma doğrusal + gürültü. Funding 8 saatte bir (kısa bacak alır).
        nakit, adet, k = oz0, {}, 0
        for i, z in enumerate(t):
            while k < len(dolum) and dolum[k][0] <= z:
                _, kim, q, p, _ = dolum[k]
                adet[kim] = adet.get(kim, 0.0) + q
                nakit -= q * p + abs(q * p) * 0.0005
                k += 1
            fy = {}
            for kim, a in adet.items():
                if abs(a) < 1e-12:
                    continue
                if kim == "BINANCEF:BTCUSDT":
                    fy[kim] = float(btc[i])
                    continue
                _, olay_ms, giris, px, getiri = next(o for o in olaylar if f"BINANCEF:{o[0]}USDT" == kim)
                ilerleme = min(1.0, max(0.0, (int(z) - giris) / (olay_ms - giris)))
                fy[kim] = px * (1 + getiri * ilerleme + float(rng.normal(0, 0.004)))
            if int(z) % (8 * SAAT) == 0 and fy:
                gelir = sum(-a * fy[kk] * 0.0001 for kk, a in adet.items() if kk in fy and a < 0)
                b.execute(insert(paper_emir_olay).values(
                    emir_id=0, kol=kol, tur="fonlama", enstruman="BINANCEF:SEIUSDT", miktar=0.0, fiyat=None, ucret=-gelir,
                    zaman_ms=int(z), ayrinti={"funding_ms": int(z), "oran": 0.0001}))
                nakit += gelir
            oz = nakit + sum(a * fy[kk] for kk, a in adet.items() if kk in fy)
            b.execute(insert(paper_ozkaynak).values(kol=kol, zaman_ms=int(z), ozkaynak=oz, nakit=nakit, fiyat=fy,
                                                    pozisyon={kk: a for kk, a in adet.items() if abs(a) > 1e-12}))


def _kilit_ham(m: Engine, veri_dizini: Path, son: int) -> None:
    """Düğümün ham depoya yazdığı iki dosyanın örneği: DefiLlama sayfası (`__NEXT_DATA__`) ve Binance exchangeInfo."""
    from tradebot.veri.depo import HamDepo

    gun0 = son // GUN * GUN
    veri = [{"tSymbol": s_, "maxSupply": 1_000_000, "name": s_, "gecko_id": s_.lower(),
             "events": [{"unlockType": "cliff", "noOfTokens": [oran * 1_000_000], "timestamp": (gun0 + g * GUN) // 1000,
                         "category": kat}]} for s_, g, oran, kat in KILIT_TAKVIM]
    html = ('<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({"props": {"pageProps": {"data": veri}}}) + "</script></html>").encode()
    perp = {"symbols": [{"contractType": "PERPETUAL", "quoteAsset": "USDT", "baseAsset": s_, "symbol": f"{s_}USDT",
                         "status": "TRADING", "onboardDate": 0, "deliveryDate": 4133404800000, "filters": []}
                        for s_ in ("BTC", "SEI", "STRK", "ARB", "ZRO", "APR", "EIGEN")]}
    h = HamDepo(veri_dizini, m)
    h.kaydet("defillama", f"unlocks/gunluk/{gun0}", html, "html")
    h.kaydet("binancef", "exchangeInfo", json.dumps(perp).encode(), "json")
