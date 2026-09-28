"""Bağımsız gözetmen (Final Doküman §Mimari 3, risk katmanı 5): motor donarsa pozisyonları kapatır.

Motordan ayrı süreçtir (compose `saglik` bekçisinin içinde koşar, paper konteynerinden bağımsız). Kural 7: riski
azaltan her şey otomatiktir; kapatılan kolların yeniden açılması Scryne'ın onayını ister (`/devam`, Telegram).

Donma: paper düğümü her saat kapanışında özkaynak işareti yazar (kalp atışı). Son işaret `DONMA_MS`'den eskiyse (iki
kapanış kaçmış) ve bu, gözetmenin art arda `ONAY_TUR` turunda gördüğü bir durumsa donma sayılır. Yanlış alarma karşı:
gözetmen kendi açılışından sonraki `ISINMA_SN` içinde kapatmaz (host kapanıp açıldığında paper birkaç dakikada kalp
atışını yeniler; o arada eski işaret donma sanılmasın).

Kapatma (paper): "aracı kurum" paper'da düğümün içindeki sandbox'tır ve donmuş süreçte ona ulaşılamaz. Gözetmen gerçek
parada yapacağı şeyi deftere yazar: defterdeki net pozisyon canlı Binance kotasyonundan (satış bid'den, alış ask'tan,
ek kayma ve komisyon aleyhte) kapanmış sayılır (`paper_emir.tur = gozetmen`, dolum `paper_emir_olay.tur = dolum`), her
kol `durdur` olayıyla durdurulur, denetim izine yazılır. Düğüm yeniden başlarsa durumu defterden kurar (düz, durdurulmuş);
donmadan kendiliğinden çözülürse `durdur` olayını görüp belleğini defterden yeniler ve sandbox'ı deftere eşitler
(`dugum.Beyin._olaylari_uygula`). Özkaynak işareti YAZILMAZ: yazılsaydı kalp atışı taze görünür, bekçi donmayı görmezdi.

Gerçek para (Faz 12): `fiyat_al` + defter yazımı yerine aracı kurum API'si üzerinden reduce-only emir (aynı akış).
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine

from tradebot import denetim
from tradebot.db import paper_emir, paper_emir_olay, paper_kol, paper_kol_olay, paper_ozkaynak
from tradebot.kayit import log

NEDEN = "gozetmen_donma"
DONMA_MS = 125 * 60_000
ONAY_TUR = 3
ISINMA_SN = 15 * 60
UCRET = 0.001      # Binance spot VIP0 taker (maliyet modeli BINANCE)
KAYMA = 0.0002     # 2 bps aleyhte (maliyet modeli BINANCE)
_log = log("gozetmen")

FiyatAl = Callable[[list[str]], dict[str, tuple[float, float]]]   # kimlikler → {kimlik: (bid, ask)}


def binance_kotasyon(http_al) -> FiyatAl:
    """Binance spot `bookTicker` (herkese açık uç, anahtar yok). `http_al(url) -> bytes`."""
    import json

    def al(kimlikler: list[str]) -> dict[str, tuple[float, float]]:
        out = {}
        for k in kimlikler:
            r = json.loads(http_al(f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={k.split(':', 1)[1]}"))
            out[k] = (float(r["bidPrice"]), float(r["askPrice"]))
        return out
    return al


def net_pozisyonlar(motor: Engine) -> dict[str, dict[str, float]]:
    """Defterdeki net pozisyon (yalnız `dolum`; toparlanma sandbox kurulumudur, deftere girmez)."""
    with motor.connect() as b:
        rows = b.execute(select(paper_emir_olay.c.kol, paper_emir_olay.c.enstruman, func.sum(paper_emir_olay.c.miktar))
                         .where(paper_emir_olay.c.tur == "dolum")
                         .group_by(paper_emir_olay.c.kol, paper_emir_olay.c.enstruman)).all()
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for kol, kim, q in rows:
        if q is not None and abs(float(q)) > 1e-9:
            out[kol][kim] = float(q)
    return dict(out)


@dataclass
class Gozetmen:
    motor: Engine
    fiyat_al: FiyatAl
    kod_surumu: str = "bilinmiyor"
    kuru: bool = False                      # tatbikat: tespit eder, raporlar, yazmaz
    donma_ms: int = DONMA_MS
    onay_tur: int = ONAY_TUR
    isinma_sn: float = ISINMA_SN
    saat: Callable[[], float] = time.time
    baslangic: float = field(init=False)
    ardisik: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.baslangic = self.saat()

    def kontrol(self) -> dict:
        """Bir tur. Döndürür: durum (`paper_yok` | `canli` | `donma_suphesi` | `donma`) ve ayrıntı."""
        simdi_ms = int(self.saat() * 1000)
        with self.motor.connect() as b:
            son = b.execute(select(func.max(paper_ozkaynak.c.zaman_ms))).scalar()
            kollar = [r[0] for r in b.execute(select(paper_kol.c.kol))]
        if son is None or not kollar:
            return {"durum": "paper_yok"}
        yas_dk = round((simdi_ms - int(son)) / 60_000, 1)
        if simdi_ms - int(son) <= self.donma_ms:
            self.ardisik = 0
            return {"durum": "canli", "yas_dk": yas_dk}
        self.ardisik += 1
        if self.saat() - self.baslangic < self.isinma_sn or self.ardisik < self.onay_tur:
            return {"durum": "donma_suphesi", "yas_dk": yas_dk, "tur": self.ardisik}
        with self.motor.connect() as b:   # bu donmada zaten durdurulmuş kollar (tekrar yazılmaz)
            durmus = {r[0] for r in b.execute(select(paper_kol_olay.c.kol).where(
                paper_kol_olay.c.tur == "durdur", paper_kol_olay.c.zaman_ms > int(son)))}
        acik = {k: v for k, v in net_pozisyonlar(self.motor).items() if k in kollar}
        durdurulacak = [k for k in kollar if k not in durmus]
        if not durdurulacak and not acik:
            return {"durum": "donma", "yas_dk": yas_dk, "kapatilan": {}, "durdurulan": []}
        if self.kuru:
            return {"durum": "donma", "yas_dk": yas_dk, "kuru": True, "kapatilacak": acik, "durdurulacak": durdurulacak}
        kimlikler = sorted({k for v in acik.values() for k in v})
        fiyat = self.fiyat_al(kimlikler) if kimlikler else {}   # hata yükselir: kapatılamadı, bir sonraki tur dener
        kapatilan = self._kapat(acik, fiyat, simdi_ms, int(son))
        for k in durdurulacak:
            self._olay(k, simdi_ms, {"neden": NEDEN, "son_isaret_ms": int(son), "kapatilan": kapatilan.get(k, {})})
        denetim.kaydet(self.motor, "gozetmen", "donma_kapatma",
                       {"son_isaret_ms": int(son), "yas_dk": yas_dk, "kapatilan": kapatilan, "durdurulan": durdurulacak})
        _log.error("motor_donmasi_kapatildi", yas_dk=yas_dk, kapatilan=kapatilan, durdurulan=durdurulacak)
        return {"durum": "donma", "yas_dk": yas_dk, "kapatilan": kapatilan, "durdurulan": durdurulacak}

    def _kapat(self, acik: dict[str, dict[str, float]], fiyat: dict[str, tuple[float, float]], simdi_ms: int,
               son_ms: int) -> dict[str, dict[str, dict]]:
        out: dict[str, dict[str, dict]] = defaultdict(dict)
        with self.motor.begin() as b:
            for kol, poz in acik.items():
                for kim, adet in poz.items():
                    q = -adet
                    bid, ask = fiyat[kim]
                    ref = bid if q < 0 else ask
                    px = ref * (1 - KAYMA) if q < 0 else ref * (1 + KAYMA)
                    ucret = abs(q) * px * UCRET
                    eid = b.execute(insert(paper_emir).values(
                        kol=kol, karar_id=None, istemci_emir_id=f"G-{uuid.uuid4().hex[:20]}", enstruman=kim, istenen=q,
                        onaylanan=q, karar_fiyati=ref, gonderim_fiyati=ref, zaman_ms=simdi_ms, tur="gozetmen",
                        risk={"onay": True, "gerekceler": [NEDEN], "risk_azaltan": True})).inserted_primary_key[0]
                    b.execute(insert(paper_emir_olay).values(
                        emir_id=eid, kol=kol, tur="dolum", enstruman=kim, miktar=q, fiyat=px, ucret=ucret, zaman_ms=simdi_ms,
                        ayrinti={"gozetmen": True, "bid": bid, "ask": ask, "son_isaret_ms": son_ms}))
                    out[kol][kim] = {"adet": q, "fiyat": px, "ucret": round(ucret, 4)}
        return dict(out)

    def _olay(self, kol: str, simdi_ms: int, ayrinti: dict) -> None:
        with self.motor.begin() as b:
            b.execute(insert(paper_kol_olay).values(kol=kol, zaman_ms=simdi_ms, tur="durdur", kod_surumu=self.kod_surumu,
                                                    ayrinti=ayrinti))
