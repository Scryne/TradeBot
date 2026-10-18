"""Paper düğümü (Faz 7): NautilusTrader LiveNode, Binance spot canlı veri + sandbox yürütme (Spike 02, 05).

Akış (her 1h bar kapanışında, `Tetik` → `Beyin.saat_kapandi`):
1. Kapanan bar REST'ten canlı depoya eklenir (`CanliBarlar`); iki enstrüman da gelmeden karar verilmez (5 sn arayla
   yeniden denenir).
2. Bu kapanışta sınırı dolan her kol (1h her saat, 4h 00/04/…, 1d 00:00 UTC) için `karar_ver` → karar deftere (emirden
   ÖNCE) → her emir `RiskMotoru.onayla` (kural 5: emre giden tek yol) → onaylıysa kolun Nautilus stratejisi piyasa emri
   gönderir → dolum/ret deftere.
   Portföy kolu en sonda karar verir: hedefi, haftalık dağıtım katsayıları × kaynak kolların bu kapanıştaki etkin
   hedefleridir (hafta döndüyse dağıtım önce hesaplanır, `canli/dagitici.py`).
3. Bütün kollar son kapanışla işaretlenir, özkaynak deftere yazılır.
4. Beş dakika sonra mutabakat: Nautilus'taki pozisyon ≠ defter → alarm, kol durdurulur (yalnız riski azaltan emir).

Başlangıç: defter kol durumlarının kaynağıdır. Sandbox boş açılır, defterdeki pozisyonlar `toparlanma` emirleriyle
kurulur (defteri ve maliyet ölçümünü değiştirmez). Son kapanmış bar için karar yoksa hemen verilir (gecikmeli işaretli).
Nautilus'a dokunan kod bu dosyada toplanır (sürüm sabit: 2.0.0rc5; Final Doküman §8).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import socket
import time
import uuid

import numpy as np
from nautilus_trader.adapters.binance import (
    BinanceDataClientConfig,
    BinanceDataClientFactory,
    BinanceEnvironment,
    BinanceInstrumentProviderConfig,
    BinanceProductType,
    BinanceSpotMarketDataMode,
)
from nautilus_trader.adapters.sandbox import SandboxExecutionClientConfig, SandboxExecutionClientFactory
from nautilus_trader.common import Environment
from nautilus_trader.config import LiveRiskEngineConfig, StrategyConfig
from nautilus_trader.execution import MakerTakerFeeModel
from nautilus_trader.live import LiveNode
from nautilus_trader.model import (
    AccountId,
    Bar,
    BarType,
    Currency,
    InstrumentId,
    Money,
    OrderSide,
    Quantity,
    StrategyId,
    TraderId,
    Venue,
)
from nautilus_trader.trading import Strategy

from tradebot.canli import dagitici as dg
from tradebot.canli import karar as kr
from tradebot.canli.bar_akisi import CanliBarlar
from tradebot.canli.defter import PaperDefter
from tradebot.canli.gozetmen import NEDEN as GOZETMEN_NEDEN
from tradebot.canli.kollar import AGRESIF, PORTFOY, PaperKol
from tradebot.kayit import log
from tradebot.risk.motor import Durum, EmirIstegi, Piyasa, Portfoy, RiskAyar, RiskMotoru
from tradebot.veri.takvim import ZAMAN_DILIMI_MS
from tradebot.zeka import nabiz
from tradebot.zeka.olay import aktif_vetolar

SAAT_MS = 3_600_000
ARDISIK_RET_SINIRI = 3  # aynı kol + enstrümanda art arda borsa reddi → kol durur (yalnız riski azaltan emir), alarm
OTOMATIK_DURDURMA = {"mutabakat", "ardisik_ret"}  # düğümün kendi durdurmaları: pozisyon tutulur
BINANCE = Venue("BINANCE")
_log = log("canli.dugum")


def nautilus_id(kimlik: str) -> InstrumentId:
    return InstrumentId.from_str(f"{kimlik.removeprefix('BINANCE:')}.BINANCE")


KACAN_KAPANIS_MS = 2 * 60_000   # bar olayı bu kadar gecikirse kapanış REST'ten işlenir (Tetik._kacan_kontrol)


def kacan_kapanis(simdi_ms: int, son_kapanis_ms: int, bekleyen: int | None) -> int | None:
    """Bar olayı gelmemiş (websocket koptu, süreç dondu/çözüldü) kapanış: işlenmesi gereken kapanış ya da None.
    2026-09-28 donma tatbikatı: konteyner saat başında donuk kaldı, çözülünce websocket 2 sn'de yeniden bağlandı ama
    kaçan barın olayı hiç gelmedi; düğüm bir sonraki saati bekledi (1h kolları bir karar atladı, kalp atışı gözetmen
    eşiğine 5 dk kala yenilendi)."""
    son = simdi_ms - simdi_ms % SAAT_MS
    if bekleyen is not None or son <= son_kapanis_ms or simdi_ms - son < KACAN_KAPANIS_MS:
        return None
    return son


def sinir_doldu(zd: str, kapanis_ms: int) -> bool:
    """Bu kapanış anında zd barı tamamlandı mı (1h her saat, 4h UTC 00/04/…, 1d 00:00)."""
    return kapanis_ms % ZAMAN_DILIMI_MS[zd] == 0


class Beyin:
    """Kolların durumu, kararlar, emir dağıtımı, işaretleme ve mutabakat. Nautilus olay döngüsünde çalışır."""

    def __init__(self, motor, kollar: list[PaperKol], defter: PaperDefter, barlar: CanliBarlar, kayit: dict,
                 nabiz_dizini=None) -> None:
        self.motor, self.kollar, self.defter, self.barlar, self.kayit = motor, kollar, defter, barlar, kayit
        self.nabiz_dizini = nabiz_dizini   # zekâ nabzı (habere kör mod); None: kontrol yok (testler, duman)
        self.kor: tuple[bool, str] = (False, "")
        self.kimlikler = sorted({k for kol in kollar for k in kol.grup["kimlikler"]})
        self.durum = {k.ad: defter.durum(k) for k in kollar}
        self.risk = {k.ad: RiskMotoru(RiskAyar(kaldirac=k.ayar.kaldirac)) for k in kollar}
        self.stratejiler: dict[str, KolStratejisi] = {}
        self.durdurulan: set[str] = set()
        # Elle (Telegram/CLI) durdurulan kol düzleşir (hedef 0; kural 7, kilit ve MT5 düğümleriyle aynı, 2026-10-05).
        # Düğümün kendi durdurmaları (mutabakat, ardışık ret) yalnız yeni riski keser, pozisyonu tutar.
        self.duzlesecek: set[str] = set()
        self.ardisik_ret: dict[tuple[str, str], int] = {}
        self.son_fiyat: dict[str, float] = {}
        self.son_kapanis_ms = 0
        self.dagitim: dict | None = None  # portföy kolunun bu haftaki dağıtımı (paper_dagitim)
        olaylar = defter.kol_olaylari()
        self._son_olay_id = olaylar[-1].id if olaylar else 0  # açılışta durum() olayları zaten uyguladı
        # Elle (Telegram/CLI) durdurulan kol yeniden başlatmada durdurulmuş kalır: son elle olay `durdur` ise. Mutabakat
        # durdurması kalkar (toparlanma sandbox'ı defterden kurar, fark ortadan kalkar).
        son_elle: dict[str, tuple[str, str | None]] = {}
        for o in olaylar:
            if o.tur == "devam" or (o.tur == "durdur" and o.ayrinti.get("neden") != "mutabakat"):
                son_elle[o.kol] = (o.tur, o.ayrinti.get("neden"))
        self.durdurulan |= {k for k, (t, _) in son_elle.items() if t == "durdur" and k in self.durum}
        self.duzlesecek |= {k for k, (t, n) in son_elle.items()
                            if t == "durdur" and k in self.durum and n not in OTOMATIK_DURDURMA}

    # ------------------------------------------------------------------ karar
    def saat_kapandi(self, kapanis_ms: int, gecikmeli: bool = False) -> bool:
        """Döndürür: tamamlandı mı (False: bar henüz REST'te yok, yeniden denenmeli)."""
        simdi = int(time.time() * 1000)
        son = self.barlar.guncelle(self.kimlikler, simdi)
        beklenen = kapanis_ms - SAAT_MS
        if any(v < beklenen for v in son.values()):
            return False
        vetolu = aktif_vetolar(self.motor, simdi)
        kor = nabiz.kor_mu(self.nabiz_dizini, simdi) if self.nabiz_dizini is not None else (False, "")
        if kor[0] != self.kor[0]:
            (_log.error if kor[0] else _log.warning)("habere_kor" if kor[0] else "habere_kor_bitti", neden=kor[1])
        self.kor = kor
        self._olaylari_uygula()
        self._duzlestir_hemen(kapanis_ms)
        self._dagitim_guncelle(kapanis_ms)
        for kol in self.kollar:
            zd_ms = ZAMAN_DILIMI_MS[kol.zd]
            sinir = kapanis_ms - kapanis_ms % zd_ms           # kolun son tamamlanmış bar sınırı
            if not gecikmeli and sinir != kapanis_ms:
                continue
            if gecikmeli and kapanis_ms - sinir >= SAAT_MS:   # geç kalınmış: sonraki sınırı bekle (parity korunur)
                if not self.defter.karar_var(kol.ad, sinir - zd_ms):  # o sınırın kararı zaten verildiyse kaçırılmadı
                    _log.warning("karar_kacirildi", kol=kol.ad, sinir_ms=sinir)
                continue
            try:
                self._kol_karar(kol, vetolu, gecikmeli, sinir, kor[0])
            except Exception as e:  # noqa: BLE001 — bir kolun hatası diğerlerini durdurmaz
                _log.error("kol_karar_hatasi", kol=kol.ad, hata=f"{type(e).__name__}: {e}"[:300])
        self._isaretle(kapanis_ms)
        self.son_kapanis_ms = kapanis_ms
        return True

    def _olaylari_uygula(self) -> None:
        """Çalışırken yazılan olaylar bir sonraki kapanışta uygulanır: onaylı `acil_kaldir` (CLI), elle `durdur` ve
        `devam` (Telegram, onaylı). Düğümün kendi yazdığı mutabakat durdurması zaten uygulanmıştır."""
        for o in self.defter.kol_olaylari(id_sonra=self._son_olay_id):
            self._son_olay_id = o.id
            if o.kol in self.durum and o.tur == "durdur" and o.ayrinti.get("neden") != "mutabakat":
                self.durdurulan.add(o.kol)
                if o.ayrinti.get("neden") not in OTOMATIK_DURDURMA:
                    self.duzlesecek.add(o.kol)
                _log.warning("kol_elle_durduruldu", kol=o.kol, neden=o.ayrinti.get("neden"))
                if o.ayrinti.get("neden") == GOZETMEN_NEDEN:
                    # Bağımsız gözetmen motor donmuş sanıp kolun pozisyonunu defterde kapattı; motor sonradan çözüldü.
                    # Defter kaynaktır: bellek defterden yeniden kurulur, sandbox toparlanmayla deftere eşitlenir.
                    kol = next(k for k in self.kollar if k.ad == o.kol)
                    self.durum[o.kol] = self.defter.durum(kol)
                    self.toparla([o.kol])
                    _log.error("gozetmen_kapatmasi_uygulandi", kol=o.kol)
            elif o.kol in self.durum and o.tur == "devam":
                self.durdurulan.discard(o.kol)
                self.duzlesecek.discard(o.kol)
                for anahtar in [x for x in self.ardisik_ret if x[0] == o.kol]:   # eski ret sayacı tek retle yeniden
                    del self.ardisik_ret[anahtar]                                # durdurmasın
                _log.warning("kol_elle_devam", kol=o.kol)
            d = self.durum.get(o.kol)
            iz = d.izleyici if d is not None else None
            if o.tur == "acil_kaldir" and iz is not None and iz.durum == Durum.ACIL_DURDURMA:
                iz.acil_durdurma_kaldir(o.ayrinti["onaylayan"], o.ayrinti["gerekce"])
                _log.warning("acil_durdurma_kaldirildi", kol=o.kol, onaylayan=o.ayrinti["onaylayan"])

    def _duzlestir_hemen(self, kapanis_ms: int) -> None:
        """Elle durdurulan kol kendi zaman dilimi sınırını beklemeden düzleşir (1d kolda 23 saate kadar gecikme vardı;
        kural 7: riski azaltan her şey hemen). Sınırdaki kol normal kararla (hedef 0) zaten düzleşir."""
        for kol in self.kollar:
            d = self.durum[kol.ad]
            if kol.ad not in self.duzlesecek or not d.adet or kapanis_ms % ZAMAN_DILIMI_MS[kol.zd] == 0:
                continue
            for kim, q in list(d.adet.items()):
                if q:
                    self.emir_ver(kol, None, kim, -q, self.son_fiyat.get(kim, 0.0) or 1.0, kapanis_ms - SAAT_MS,
                                  Durum.NORMAL, set(), "durdur")
            _log.warning("durdurulan_kol_duzlestirildi", kol=kol.ad)

    def _dagitim_guncelle(self, kapanis_ms: int) -> None:
        """Hafta döndüyse (ya da açılışta) dağıtımı defterden okur ya da hesaplayıp yazar. Hata: katsayılar sıfır
        (portföy düzleşir: belirsizlikte riski azalt) ve alarm."""
        pf = next((k for k in self.kollar if k.strateji == PORTFOY), None)
        hafta = dg.hafta_basi(kapanis_ms)
        if pf is None or (self.dagitim is not None and self.dagitim.get("hafta_ms") == hafta):
            return
        kaynaklar = [k for k in self.kollar if k.ad in pf.parametre["kaynaklar"]]
        try:
            self.dagitim = self.defter.dagitim_getir(pf, kaynaklar, hafta)
            _log.info("dagitim", hafta_ms=hafta, kaldirac=round(self.dagitim["kaldirac"], 4),
                      golge=round(self.dagitim["kaldirac_golge"], 4), uygun=len(self.dagitim["uygun"]))
        except Exception as e:  # noqa: BLE001
            # hafta_ms None: hata o hafta için kalıcı olmasın, sonraki kapanışta yeniden denenir (bu arada portföy düz)
            self.dagitim = {"hafta_ms": None, "kollar": {}, "kaldirac": 0.0, "hata": str(e)[:300]}
            _log.error("dagitim_hatasi_portfoy_duz", hata=f"{type(e).__name__}: {e}"[:300])

    def _kol_karar(self, kol: PaperKol, vetolu: set[str], gecikmeli: bool, sinir_ms: int, kor: bool = False) -> None:
        h = kr.hazirla(self.barlar.canli, self.kayit, kol, bit_ms=sinir_ms)  # yalnız tamamlanmış zd barları
        bar_ms = int(h.g.t[-1])
        if self.defter.karar_var(kol.ad, bar_ms):
            return
        d = self.durum[kol.ad]
        hedef = None
        if kol.strateji == AGRESIF:
            kaynaklar = [k for k in self.kollar if k.ad in kol.parametre["kaynaklar"]]
            hedef = kr.agresif_hedef(self.barlar.canli, self.kayit, kol, kaynaklar, sinir_ms)
        elif kol.strateji == PORTFOY:  # kaynaklar bu kapanıştaki kararlarını verdi (liste sırası: portföy en sonda)
            katsayi = {k: v["katsayi"] for k, v in (self.dagitim or {}).get("kollar", {}).items()}
            hedef = dg.portfoy_hedef(katsayi, {k: self.durum[k].onceki_h for k in katsayi}, list(h.g.kimlikler),
                                     RiskAyar(kaldirac=kol.ayar.kaldirac).enstruman_tavani, kol.yon == "long_short")
        if kol.ad in self.duzlesecek:
            hedef = np.zeros(len(h.g.kimlikler))
        k = kr.karar_ver(kol, h, d, vetolu, hedef, habere_kor=kor)
        kid = self.defter.karar_yaz(k, h.g.veri_hash, gecikmeli)
        d.onceki_h = dict(zip(k.kimlikler, (float(x) for x in k.etkin_hedef), strict=True))
        d.ilk = False
        _log.info("karar", kol=kol.ad, bar_ms=bar_ms, durum=k.durum, yeni=[round(float(x), 4) for x in k.yeni],
                  emir=len(k.miktar), gecikmeli=gecikmeli)
        for j, kim in enumerate(k.kimlikler):
            q = k.miktar.get(kim)
            if q:
                self.emir_ver(kol, kid, kim, q, float(k.fiyat[j]), bar_ms, Durum(k.durum), vetolu, "karar")

    def emir_ver(self, kol: PaperKol, karar_id: int | None, kim: str, q: float, fiyat: float, bar_ms: int, durum: Durum,
                 vetolu: set[str], tur: str) -> None:
        s = self.stratejiler[kol.ad]
        d = self.durum[kol.ad]
        adim = s.adim(kim)
        risk_id = f"{kol.ad}|{bar_ms}|{kim}|{tur}|{uuid.uuid4().hex[:8]}"
        pf = Portfoy(ozkaynak=d.ozkaynak, pozisyonlar=dict(d.adet),
                     fiyatlar={k: self.son_fiyat.get(k, fiyat) for k in self.kimlikler},
                     siniflar={k: "kripto" for k in self.kimlikler}, durum=durum,
                     durdurulan_kollar={kol.ad} if kol.ad in self.durdurulan else set(),
                     veto=vetolu if kol.jev else set())
        p = Piyasa(son_fiyat=self.son_fiyat.get(kim, fiyat), son_bar_ms=bar_ms, bar_ms=ZAMAN_DILIMI_MS[kol.zd], acik=True,
                   adim_miktar=adim)
        e = EmirIstegi(kim, "kripto", q, fiyat, kol.ad, int(time.time() * 1000), risk_id)
        if tur == "toparlanma":  # defterdeki pozisyonu sandbox'ta kurmak: risk değişmez, yalnız akıl kontrolleri
            onay = abs(q) >= adim
            karar_risk = {"onay": onay, "gerekceler": ["toparlanma"], "risk_azaltan": False}
            miktar = q
        else:
            rk = self.risk[kol.ad].onayla(e, p, pf)
            karar_risk = {"onay": rk.onay, "gerekceler": list(rk.gerekceler), "risk_azaltan": rk.risk_azaltan}
            miktar = rk.miktar if rk.onay else 0.0
        miktar = s.yuvarla(kim, miktar)
        if not miktar:
            self.defter.emir_yaz(kol.ad, karar_id, f"RED-{uuid.uuid4().hex[:16]}", kim, q, 0.0, fiyat, tur,
                                 karar_risk | {"onay": False, "lot_alti": karar_risk["onay"]})
            _log.warning("emir_gonderilmedi", kol=kol.ad, enstruman=kim, istenen=q, risk=karar_risk)
            return
        s.gonder(karar_id, kim, q, miktar, fiyat, tur, karar_risk)

    # ------------------------------------------------------------------ dolum, işaretleme, mutabakat
    def ret(self, kol_ad: str, kim: str, neden: str) -> None:
        """Borsa/sandbox reddi. Art arda `ARDISIK_RET_SINIRI` ret: kol durur (A6'nın kod tarafı; ret kodları yapısal,
        Jev yalnız tanınmayan serbest metin için Faz 8'de, gerçek MT5 ret örnekleriyle). Dolum sayacı sıfırlar."""
        n = self.ardisik_ret.get((kol_ad, kim), 0) + 1
        self.ardisik_ret[(kol_ad, kim)] = n
        if n >= ARDISIK_RET_SINIRI and kol_ad not in self.durdurulan:
            self.durdurulan.add(kol_ad)
            self.defter.kol_olay_yaz(kol_ad, "durdur", {"neden": "ardisik_ret", "enstruman": kim, "sayi": n,
                                                        "son_neden": neden[:300]})
            _log.error("ardisik_ret_kol_durdu", kol=kol_ad, enstruman=kim, sayi=n, neden=neden[:200])

    def dolum(self, kol_ad: str, kim: str, q: float, px: float, ucret: float, tur: str) -> None:
        self.ardisik_ret.pop((kol_ad, kim), None)
        if tur == "toparlanma":
            return  # defterde pozisyon zaten var
        d = self.durum[kol_ad]
        d.adet[kim] = d.adet.get(kim, 0.0) + q
        if abs(d.adet[kim]) < 1e-12:
            del d.adet[kim]
        d.nakit -= q * px + ucret

    def _isaretle(self, kapanis_ms: int) -> None:
        fiyat = {}
        for k in self.kimlikler:
            df = self.barlar.canli.oku(k, "1h")
            fiyat[k] = float(df["close"][-1])
        self.son_fiyat |= fiyat
        for kol in self.kollar:
            d = self.durum[kol.ad]
            d.isaretle(fiyat)
            self.defter.ozkaynak_yaz(kol.ad, kapanis_ms, d, fiyat)

    def mutabakat(self) -> dict[str, dict]:
        farklar = {}
        for kol in self.kollar:
            s = self.stratejiler[kol.ad]
            d = self.durum[kol.ad]
            for kim in self.kimlikler:
                nt, dft = s.pozisyon(kim), d.adet.get(kim, 0.0)
                if abs(nt - dft) > max(s.adim(kim), 1e-9) * 1.5:
                    farklar.setdefault(kol.ad, {})[kim] = {"nautilus": nt, "defter": dft}
        for kol_ad, f in farklar.items():
            if kol_ad not in self.durdurulan:
                self.durdurulan.add(kol_ad)
                self.defter.kol_olay_yaz(kol_ad, "durdur", {"neden": "mutabakat", "fark": f})
                _log.error("mutabakat_farki_kol_durdu", kol=kol_ad, fark=f)
        return farklar

    def toparla(self, kol_adlari: list[str] | None = None) -> None:
        """Sandbox'ı deftere eşitler (tur=toparlanma): açılışta boş sandbox'a defterdeki pozisyonlar kurulur; gözetmen
        kapatmasından sonra sandbox'ta kalan pozisyon kapatılır (bu yüzden bütün enstrümanlarda fark alınır)."""
        for kol in self.kollar:
            if kol_adlari is not None and kol.ad not in kol_adlari:
                continue
            d = self.durum[kol.ad]
            s = self.stratejiler[kol.ad]
            for kim in sorted(set(self.kimlikler) | set(d.adet)):
                fark = d.adet.get(kim, 0.0) - s.pozisyon(kim)
                if abs(fark) >= s.adim(kim):
                    self.emir_ver(kol, None, kim, fark, self.son_fiyat.get(kim, 0.0) or 1.0, 0, Durum.NORMAL, set(),
                                  "toparlanma")


# ---------------------------------------------------------------------- Nautilus stratejileri
class Tetik(Strategy):
    """1h bar kapanışlarını ve kotasyonları dinler; kararı Beyin'e yaptırır."""

    # Nautilus v2: strateji kurucusu yalnız config alır; beyin `bagla` ile sonradan verilir.
    def bagla(self, beyin: Beyin) -> Tetik:
        self.beyin = beyin
        self.bar_tipleri = [BarType.from_str(f"{nautilus_id(k)}-1-HOUR-LAST-EXTERNAL") for k in beyin.kimlikler]
        self._bekleyen: int | None = None
        return self

    def on_start(self) -> None:
        for k in self.beyin.kimlikler:
            iid = nautilus_id(k)
            # Yalnız kotasyon: sandbox dolumu alışta ask, satışta bid'e karşı (aleyhte, kural 4). İşlem akışı da
            # eşleştirilince geç gelen her işlem için "stale trade" uyarısı basılıyordu (8 saatte ~286 bin satır).
            self.subscribe_quotes(iid)
        for bt in self.bar_tipleri:
            self.subscribe_bars(bt)
        self.clock.set_time_alert("toparlanma", self.clock.utc_now() + dt.timedelta(seconds=30), self._baslangic)
        self._basladi = False
        self.clock.set_timer("kacan-kapanis", dt.timedelta(minutes=1), callback=self._kacan_kontrol)

    def on_quote(self, q) -> None:
        kim = f"BINANCE:{q.instrument_id.symbol.value}"
        self.beyin.son_fiyat[kim] = (float(q.bid_price) + float(q.ask_price)) / 2

    def _kacan_kontrol(self, _event) -> None:
        if not self._basladi:
            return
        k = kacan_kapanis(int(time.time() * 1000), self.beyin.son_kapanis_ms, self._bekleyen)
        if k is not None:
            _log.warning("kacan_kapanis_islendi", kapanis_ms=k)
            self._dene(k, gecikmeli=True)

    def _baslangic(self, _event) -> None:
        self._basladi = True
        self.beyin.toparla()
        simdi = int(time.time() * 1000)
        son_kapanis = simdi - simdi % SAAT_MS
        self._dene(son_kapanis, gecikmeli=True)

    def on_bar(self, bar: Bar) -> None:
        ts = bar.ts_event // 1_000_000
        kapanis_ms = (ts + SAAT_MS // 2) // SAAT_MS * SAAT_MS  # Binance kline kapanışı açılış + 1 sa − 1 ms
        if kapanis_ms <= self.beyin.son_kapanis_ms or self._bekleyen == kapanis_ms:
            return
        self._dene(kapanis_ms)

    def _dene(self, kapanis_ms: int, gecikmeli: bool = False, deneme: int = 0) -> None:
        self._bekleyen = kapanis_ms
        try:
            tamam = self.beyin.saat_kapandi(kapanis_ms, gecikmeli)
        except Exception as e:  # noqa: BLE001 — REST/DB hatası kapanışı kaybettirmesin: yeniden denenir
            _log.error("kapanis_hatasi", kapanis_ms=kapanis_ms, deneme=deneme, hata=f"{type(e).__name__}: {e}"[:200])
            tamam = False
        if tamam:
            self._bekleyen = None
            self.clock.set_time_alert(f"mutabakat-{kapanis_ms}", self.clock.utc_now() + dt.timedelta(minutes=5),
                                      lambda _e: self.beyin.mutabakat())
            return
        if deneme >= 60:
            _log.error("bar_gelmedi", kapanis_ms=kapanis_ms)
            self._bekleyen = None
            return
        self.clock.set_time_alert(f"yeniden-{kapanis_ms}-{deneme}", self.clock.utc_now() + dt.timedelta(seconds=5),
                                  lambda _e: self._dene(kapanis_ms, gecikmeli, deneme + 1))


class KolStratejisi(Strategy):
    """Bir paper kolu: kendi pozisyonları (Nautilus'ta strateji başına ayrı), emir gönderme, dolum ve ret kaydı."""

    def bagla(self, kol: PaperKol, beyin: Beyin) -> KolStratejisi:
        self.kol, self.beyin = kol, beyin
        self._emirler: dict[str, tuple[int, str, str]] = {}  # client_order_id → (emir_id, kimlik, tur)
        self._poz: dict[str, float] = {}  # Nautilus'un bildirdiği dolumlardan (toparlanma dahil) net adet
        return self

    def _enstruman(self, kim: str):
        return self.cache.instrument(nautilus_id(kim))

    def adim(self, kim: str) -> float:
        i = self._enstruman(kim)
        return float(i.size_increment) if i is not None else 1e-5

    def yuvarla(self, kim: str, q: float) -> float:
        i = self._enstruman(kim)
        if i is None or not q:
            return 0.0
        adim = float(i.size_increment)
        n = int(abs(q) / adim + 1e-9)
        a = round(n * adim, i.size_precision)
        if i.min_quantity is not None and a < float(i.min_quantity):
            return 0.0
        return a if q > 0 else -a

    def pozisyon(self, kim: str) -> float:
        """Bu stratejinin Nautilus dolum olaylarından net adedi (sandbox yeniden başlatmada sıfırdan başlar)."""
        return self._poz.get(kim, 0.0)

    def gonder(self, karar_id: int | None, kim: str, istenen: float, q: float, fiyat: float, tur: str, risk: dict) -> None:
        i = self._enstruman(kim)
        emir = self.order_factory.market(nautilus_id(kim), OrderSide.BUY if q > 0 else OrderSide.SELL,
                                         Quantity(abs(q), i.size_precision))
        cid = emir.client_order_id.value
        eid = self.beyin.defter.emir_yaz(self.kol.ad, karar_id, cid, kim, istenen, q, fiyat, tur, risk,
                                         self.beyin.son_fiyat.get(kim))
        self._emirler[cid] = (eid, kim, tur)
        self.submit_order(emir)

    def on_order_filled(self, event) -> None:
        kayit = self._emirler.get(event.client_order_id.value)
        if kayit is None:
            return
        eid, kim, tur = kayit
        q = float(event.last_qty) * (1 if event.order_side == OrderSide.BUY else -1)
        px = float(event.last_px)
        ucret = event.commission.as_double()
        if event.commission.currency.code != "USDT":  # taban para biriminde kesilen komisyon → USDT
            ucret *= px
        # Önce Nautilus'un gerçeği: defter yazımı düşerse bellek defterle aynı kalır ve mutabakat farkı görüp kolu
        # durdurur (eskiden ikisi birden atlanıyor, fark hiç görünmüyordu; 2026-10-18 denetimi).
        self._poz[kim] = self._poz.get(kim, 0.0) + q
        try:
            self.beyin.defter.olay_yaz(eid, self.kol.ad, "dolum" if tur != "toparlanma" else "toparlanma", kim, q, px,
                                       ucret, event.ts_event // 1_000_000, {"komisyon_para": event.commission.currency.code})
        except Exception as e:  # noqa: BLE001
            _log.error("dolum_deftere_yazilamadi", kol=self.kol.ad, enstruman=kim, miktar=q, fiyat=px,
                       hata=f"{type(e).__name__}: {e}"[:200])
            return
        self.beyin.dolum(self.kol.ad, kim, q, px, ucret, tur)

    def _ret(self, event, tur: str) -> None:
        kayit = self._emirler.get(event.client_order_id.value)
        if kayit is None:
            return
        eid, kim, _ = kayit
        self.beyin.defter.olay_yaz(eid, self.kol.ad, tur, kim, 0.0, None, 0.0, event.ts_event // 1_000_000,
                                   {"neden": str(getattr(event, "reason", ""))[:500]})
        _log.error("emir_reddedildi", kol=self.kol.ad, enstruman=kim, tur=tur, neden=str(getattr(event, "reason", ""))[:200])
        self.beyin.ret(self.kol.ad, kim, str(getattr(event, "reason", "")))

    def on_order_rejected(self, event) -> None:
        self._ret(event, "ret")

    def on_order_denied(self, event) -> None:
        self._ret(event, "ret")


# ---------------------------------------------------------------------- kurulum
def dns_isit(adlar=("stream.binance.com", "api.binance.com", "data-stream.binance.vision")) -> None:
    """Spike 02: bazı ağlarda ilk DNS çözümlemesi ~11 sn, Nautilus WS zaman aşımı 5 sn → önceden çözümle."""
    for h in adlar:
        try:
            socket.getaddrinfo(h, 443)
        except OSError as e:
            _log.warning("dns_isitma", ad=h, hata=str(e))


def kur(beyin: Beyin, bakiye_usdt: float = 10_000_000.0):
    node = (
        LiveNode.builder("TRADEBOT-PAPER", TraderId.from_str("PAPER-001"), Environment.SANDBOX)
        .with_reconciliation(reconciliation=False)
        .with_risk_engine_config(LiveRiskEngineConfig(bypass=False))
        .add_data_client(None, BinanceDataClientFactory(), BinanceDataClientConfig(
            product_type=BinanceProductType.SPOT, environment=BinanceEnvironment.LIVE,
            spot_market_data_mode=BinanceSpotMarketDataMode.Json,
            instrument_provider=BinanceInstrumentProviderConfig(
                load_all=False,
                load_ids=[str(nautilus_id(k)) for k in beyin.kimlikler])))
        .add_simulated_exec_client("BINANCE", SandboxExecutionClientFactory(), SandboxExecutionClientConfig(
            venue=BINANCE, starting_balances=[Money(bakiye_usdt, Currency.from_str("USDT"))],
            account_id=AccountId.from_str("BINANCE-PAPER-001"), fee_model=MakerTakerFeeModel(), bar_execution=False,
            trade_execution=False))
        .build()
    )
    node.add_strategy(Tetik(StrategyConfig(strategy_id=StrategyId("TETIK-000"), order_id_tag="000")).bagla(beyin))
    for i, kol in enumerate(beyin.kollar, start=1):
        s = KolStratejisi(StrategyConfig(strategy_id=StrategyId(f"KOL-{i:03d}"), order_id_tag=f"{i:03d}")).bagla(kol, beyin)
        beyin.stratejiler[kol.ad] = s
        node.add_strategy(s)
    return node


def calistir(sure_sn: float | None = None, duman: bool = False) -> None:
    """Paper düğümünü başlatır (compose `paper` servisi). `sure_sn`: süre sınırı. `duman`: defter ayrı SQLite dosyasında,
    canlı bar deposu ayrı dizinde (asıl defter yalnız eklenir; deneme koşusu onu kirletmemeli)."""
    from tradebot.ayar import ayarlar
    from tradebot.canli.kollar import kollar as kol_listesi
    from tradebot.db import motor as db_motor
    from tradebot.veri import enstruman as en
    from tradebot.veri.depo import BarDepo, HamDepo

    a = ayarlar()
    m = db_motor(a)
    kod = os.environ.get("TRADEBOT_KOD_SURUMU", "yerel")
    ks = kol_listesi()
    canli_dizin = a.veri_dizini / ("canli_duman" if duman else "canli")
    if duman:
        from sqlalchemy import create_engine

        from tradebot.db import metadata

        dm = create_engine(f"sqlite:///{a.veri_dizini / 'paper_duman.db'}")
        metadata.create_all(dm)
        defter = PaperDefter(dm, kod + "+duman")
    else:
        defter = PaperDefter(m, kod)
    simdi = int(time.time() * 1000)
    for kol in ks:
        if defter.kol_ac(kol, simdi):
            _log.info("kol_acildi", kol=kol.ad)
    barlar = CanliBarlar(BarDepo(a.veri_dizini), BarDepo(canli_dizin), HamDepo(a.veri_dizini, m))
    kayit = {k["kimlik"]: k for k in en.hepsi(m)}
    beyin = Beyin(m, ks, defter, barlar, kayit, nabiz_dizini=None if duman else a.veri_dizini)
    barlar.hazirla(beyin.kimlikler, simdi)
    dns_isit()
    node = kur(beyin)

    async def ana() -> None:
        gorev = asyncio.create_task(node.run_async())
        if sure_sn is None:
            await gorev
            return
        await asyncio.sleep(sure_sn)
        node.handle().stop()
        try:
            await asyncio.wait_for(gorev, timeout=60)
        except Exception as e:  # noqa: BLE001
            _log.warning("durdurma", hata=str(e)[:200])

    try:
        asyncio.run(ana())
    finally:
        node.dispose()
