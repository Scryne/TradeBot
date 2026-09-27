"""B → A terfi değerlendirmesi (Faz 7; ölçüt `docs/Paper-Tasarim.md` §B → A terfi ölçütü).

Terfi "üstünlük kanıtlandı" değil, "yürütme çalışıyor ve paper backtest'le çelişmiyor" demektir. Hepsi gerekir:
1. ≥ 56 gün paper, kesinti payı < %2 (beklenen saatlik özkaynak işaretlerinden eksik olanlar).
2. Kapılar paper'da: en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30.
3. Uygulama uyumu: aynı dönemin backtest'iyle (canlı bar deposu, aynı parametre, turnuvanın kendi fonksiyonları) günlük
   getirilerde yıllık takip hatası ≤ %5; yürütme maliyeti ≤ 1,5 × modelin taraf başı varsayımı.
4. Çelişki yok: paper haftalık ortalamasının, backtest'in tüm geçmişteki haftalık dağılımına göre t ≥ −2.

Paper'da terfi otomatiktir (Final Doküman §5): bekçi haftalık raporla birlikte değerlendirir, geçen B kolu için
`terfi` olayı yazar; dağıtım olayı bir sonraki hafta başında görür. Backtest'te Jev vetosu uygulanmaz (BTC/ETH'de veto
çok nadir; Jev'li kopyanın farkı haftalık raporda ayrıca izlenir).
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from tradebot.canli import dagitici as dg

SAAT_MS = 3_600_000


def haftalik(gunluk: dict[int, float]) -> dict[int, float]:
    """Günlük log getirilerden haftalık (Pazartesi başlangıçlı) log getiri."""
    h: dict[int, float] = defaultdict(float)
    for g, r in gunluk.items():
        h[dg.hafta_basi(g)] += r
    return dict(sorted(h.items()))


def en_kotu_dusus(isaret: list[tuple[int, float]], baslangic: float) -> float:
    tepe, dd = baslangic, 0.0
    for _, o in isaret:
        tepe = max(tepe, o)
        dd = min(dd, o / tepe - 1)
    return dd


def kesinti_payi(isaret: list[tuple[int, float]], bas_ms: int, bit_ms: int) -> float:
    """Beklenen saatlik işaretlerden eksik olanların payı ([bas, bit) içinde, ilk tam saatten)."""
    ilk = bas_ms - bas_ms % SAAT_MS + SAAT_MS
    beklenen = max(0, (bit_ms - ilk) // SAAT_MS)
    if beklenen == 0:
        return 0.0
    var = len({t - t % SAAT_MS for t, _ in isaret if ilk <= t < bit_ms})
    return max(0.0, 1 - var / beklenen)


def degerlendir(paper_gunluk: dict[int, float], bt_gunluk: dict[int, float], bt_haftalik_tum: list[float],
                dusus: float, kesinti: float, gun: float, yurutme_bps: float | None, varsayim_bps: float) -> dict:
    """Saf: dört ölçüt. Döndürür: {olcutler: {ad: {deger, esik, gecti}}, gecti}."""
    ph = [math.expm1(x) for x in haftalik(paper_gunluk).values()]
    ortak = sorted(set(paper_gunluk) & set(bt_gunluk))
    fark = np.array([paper_gunluk[g] - bt_gunluk[g] for g in ortak])
    te = float(fark.std(ddof=1) * math.sqrt(dg.YIL_GUN)) if len(fark) > 1 else float("inf")
    bh = np.array(bt_haftalik_tum)
    t = (float((np.mean(ph) - bh.mean()) / (bh.std(ddof=1) / math.sqrt(len(ph))))
         if len(ph) and len(bh) > 1 and bh.std(ddof=1) > 0 else float("-inf"))
    o = {
        "sure_gun": {"deger": gun, "esik": ">= 56", "gecti": gun >= 56},
        "kesinti": {"deger": kesinti, "esik": "< 0.02", "gecti": kesinti < 0.02},
        "en_kotu_hafta": {"deger": min(ph) if ph else None, "esik": ">= -0.10", "gecti": bool(ph) and min(ph) >= -0.10},
        "en_kotu_dusus": {"deger": dusus, "esik": ">= -0.30", "gecti": dusus >= -0.30},
        "takip_hatasi": {"deger": te, "esik": "<= 0.05", "gecti": te <= 0.05, "ortak_gun": len(ortak)},
        "yurutme_maliyeti_bps": {"deger": yurutme_bps, "esik": f"<= {1.5 * varsayim_bps:.1f}",
                                 "gecti": yurutme_bps is not None and yurutme_bps <= 1.5 * varsayim_bps},
        "celiski_t": {"deger": t, "esik": ">= -2", "gecti": t >= -2},
    }
    return {"olcutler": o, "gecti": all(x["gecti"] for x in o.values())}


def kol_degerlendir(motor, depo, kayit: dict, kol, bit_ms: int) -> dict:
    """Bir paper kolunu [başlangıç, bit_ms) üzerinde değerlendirir (defter + aynı dönemin backtest'i)."""
    from tradebot.arastirma import turnuva as tv
    from tradebot.canli import rapor
    from tradebot.canli.defter import PaperDefter

    df = PaperDefter(motor, "terfi")
    bas = df.kol_baslangic(kol.ad)
    isaret = df.ozkaynak_gecmisi(kol.ad, bit_ms + 1)          # hafta başındaki (00:00) işaret dahil
    paper_g = dg.gunluk_getiri(isaret, bit_ms, dahil=True)
    v = rapor.topla(motor, bas, bit_ms)
    yur, _ = rapor.maliyet_bps([d for d in v["dolumlar"] if d["kol"] == kol.ad])

    h = tv.grup_hazirla(depo, kayit, kol.grup, kol.zd, bit_ms=bit_ms)
    p = tv.cevir(kol.parametre, tv.bar_gun(kol.zd, h.takvim))
    ayar = kol.ayar.__class__(**{**kol.ayar.__dict__, "jev_veto": False})
    s = tv.kos(h, tv.hedef_uret(h, kol.strateji, p, kol.yon, ayar), ayar)
    bt_g: dict[int, float] = defaultdict(float)
    for ti, r in zip(s.t, s.net, strict=True):             # bar kapanış gününe (paper işaretiyle aynı)
        k = int(ti) + h.g.bar_ms - 1
        bt_g[k - k % dg.GUN_MS] += math.log1p(r)
    bt_donem = {g: r for g, r in bt_g.items() if g in paper_g}
    bt_h = [math.expm1(x) for x in haftalik(dict(bt_g)).values()]
    varsayim = float(np.mean([m.taraf_bps() for m in h.modeller]))
    r = degerlendir(paper_g, bt_donem, bt_h, en_kotu_dusus(isaret, kol.baslangic_ozkaynak),
                    kesinti_payi(isaret, bas, bit_ms), (bit_ms - bas) / dg.GUN_MS, yur, varsayim)
    return r | {"kol": kol.ad, "bit_ms": bit_ms}


def hafta_degerlendir(motor, veri_dizini, kollar: list, bit_ms: int) -> list[dict]:
    """Bekçi (haftalık): 56 günü dolduran B kollarını değerlendirir; geçene `terfi` olayı yazar (paper'da otomatik,
    Final Doküman §5). Sonuçlar data/rapor/terfi-<hafta>.json. Kol hatası diğerlerini durdurmaz."""
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from tradebot.canli.defter import PaperDefter
    from tradebot.veri import enstruman as en
    from tradebot.veri.depo import BarDepo

    df = PaperDefter(motor, "terfi")
    depo = BarDepo(Path(veri_dizini) / "canli")
    kayit = {k["kimlik"]: k for k in en.hepsi(motor)}
    out = []
    for k in kollar:
        bas = df.kol_baslangic(k.ad)
        if bas is None or df.sinif(k) != "B" or (bit_ms - bas) / dg.GUN_MS < 56:
            continue
        try:
            r = kol_degerlendir(motor, depo, kayit, k, bit_ms)
        except Exception as e:  # noqa: BLE001
            out.append({"kol": k.ad, "hata": f"{type(e).__name__}: {e}"[:300]})
            continue
        if r["gecti"]:
            df.kol_olay_yaz(k.ad, "terfi", {"eski": "B", "yeni": "A", "gerekce": "paper terfi ölçütü (otomatik)",
                                            "olcutler": r["olcutler"]})
        out.append(r)
    if out:
        ad = datetime.fromtimestamp(bit_ms / 1000, UTC).date().isoformat()
        yol = Path(veri_dizini) / "rapor" / f"terfi-{ad}.json"
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out
