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

MT5 düğümleri (`doviz`, `altin`; 2026-09-30): aracı kurum (MT5 demo hesabı) düğümden bağımsızdır ve donmada da
erişilebilir. Gözetmen bu düğümlerde deftere yazmaz; kolun sihirli sayısıyla açık pozisyonları köprüden GERÇEKTEN
kapatır (ters emir, riski azaltan) ve kolu durdurur. Düğüm geri gelince bu kapanış işlemlerini bilet numarasıyla
deftere işler (`_benimse`): defter tek kaynaktan, MT5'ten beslenir.
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
    """Binance `bookTicker` (herkese açık uç, anahtar yok): `BINANCE:` spot, `BINANCEF:` USDT-M perp. `http_al(url) -> bytes`."""
    import json

    def al(kimlikler: list[str]) -> dict[str, tuple[float, float]]:
        out = {}
        for k in kimlikler:
            borsa, sembol = k.split(":", 1)
            kok = "https://fapi.binance.com/fapi/v1" if borsa == "BINANCEF" else "https://api.binance.com/api/v3"
            r = json.loads(http_al(f"{kok}/ticker/bookTicker?symbol={sembol}"))
            out[k] = (float(r["bidPrice"]), float(r["askPrice"]))
        return out
    return al


def dugum_kollari(motor: Engine) -> dict[str, list[str]]:
    """Kollar süreçlerine göre: `paper` (Nautilus düğümü, saatlik) ve ayrı düğümler (tanımda `grup_tanim.dugum`, ör.
    `kilit`). Her düğümün kalp atışı ayrı izlenir: birinin işareti ötekinin donmasını gizlemesin."""
    with motor.connect() as b:
        rows = b.execute(select(paper_kol.c.kol, paper_kol.c.tanim)).all()
    out: dict[str, list[str]] = defaultdict(list)
    for kol, t in rows:
        out[((t or {}).get("grup_tanim") or {}).get("dugum", "paper")].append(kol)
    return dict(out)


def son_isaret_ms(motor: Engine, dugum: str) -> int | None:
    """Düğümün son özkaynak işareti. `paper`: başka düğüme ait olmayan bütün işaretler (kaydı olmayan kol dahil);
    diğerleri: yalnız kendi kolları."""
    g = dugum_kollari(motor)
    q = select(func.max(paper_ozkaynak.c.zaman_ms))
    if dugum == "paper":
        baska = [k for d, ks in g.items() if d != "paper" for k in ks]
        q = q.where(paper_ozkaynak.c.kol.not_in(baska)) if baska else q
    elif g.get(dugum):
        q = q.where(paper_ozkaynak.c.kol.in_(g[dugum]))
    else:
        return None
    with motor.connect() as b:
        son = b.execute(q).scalar()
    return None if son is None else int(son)


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
    dugum: str = "paper"                    # izlenen süreç (dugum_kollari); her düğüme ayrı gözetmen
    mt5: object | None = None               # MT5 düğümü: köprü istemcisi (Mt5Istemci); kapatma köprüden
    magic: int | None = None                # MT5 düğümünün sihirli sayısı
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
        kollar = dugum_kollari(self.motor).get(self.dugum, [])
        son = son_isaret_ms(self.motor, self.dugum)
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
        durdurulacak = [k for k in kollar if k not in durmus]
        if self.mt5 is not None:
            return self._mt5_donma(simdi_ms, int(son), yas_dk, durdurulacak)
        acik = {k: v for k, v in net_pozisyonlar(self.motor).items() if k in kollar}
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

    def _mt5_donma(self, simdi_ms: int, son: int, yas_dk: float, durdurulacak: list[str]) -> dict:
        """MT5 düğümü dondu: kolun sihirli sayısıyla açık net pozisyonlar köprüden kapatılır, kol durdurulur."""
        net: dict[str, float] = defaultdict(float)
        for x in self.mt5.pozisyonlar(self.magic):          # hata yükselir: kapatılamadı, bir sonraki tur dener
            net[x["sembol"]] += float(x["hacim"])
        net = {s: round(v, 8) for s, v in net.items() if abs(v) > 1e-9}
        if not net and not durdurulacak:
            return {"durum": "donma", "yas_dk": yas_dk, "kapatilan": {}, "durdurulan": []}
        if self.kuru:
            return {"durum": "donma", "yas_dk": yas_dk, "kuru": True, "kapatilacak": net, "durdurulacak": durdurulacak}
        kapatilan: dict[str, dict] = {}
        for sembol, lot in sorted(net.items()):
            r = self.mt5.emir(sembol, -lot, f"GZ{simdi_ms // 60_000}-{sembol}"[:31], self.magic)
            tamam = [x for x in r.get("sonuc", []) if x.get("retcode") in (10008, 10009, 10010)]
            kapatilan[sembol] = {"adet": -lot, "fiyat": tamam[-1].get("fiyat") if tamam else None, "tamam": bool(tamam)}
        kol = durdurulacak[0] if len(durdurulacak) == 1 else self.dugum
        for k in durdurulacak:
            self._olay(k, simdi_ms, {"neden": NEDEN, "son_isaret_ms": son, "kapatilan_mt5": kapatilan})
        denetim.kaydet(self.motor, "gozetmen", "donma_kapatma_mt5",
                       {"dugum": self.dugum, "son_isaret_ms": son, "yas_dk": yas_dk, "kapatilan": kapatilan,
                        "durdurulan": durdurulacak})
        _log.error("mt5_dugum_donmasi_kapatildi", dugum=self.dugum, yas_dk=yas_dk, kapatilan=kapatilan)
        eksik = [s for s, v in kapatilan.items() if not v["tamam"]]
        if eksik:
            raise RuntimeError(f"MT5 kapatma tamamlanamadı: {eksik}")
        return {"durum": "donma", "yas_dk": yas_dk, "kapatilan": {kol: kapatilan} if kapatilan else {},
                "durdurulan": durdurulacak}

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
