"""Paper kararı: turnuvanın fonksiyonlarıyla, son KAPANMIŞ bar için (kural 3: vektörel tarama ve canlı aynı fonksiyon).

Zincir: `turnuva.grup_hazirla` (canlı bar deposu) → `turnuva.hedef_uret` (sinyal + oynaklık hedefi) → son satır →
`panel.dengele_adim` (bant, fren, veto; backtest döngüsünün aynısı). Emir miktarı = (yeni ağırlık − kaymış ağırlık) ×
özkaynak / fiyat. Karar bar kapanışında verilir, emir hemen gider ve sonraki barın açılışında dolar (kural 4).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from tradebot.arastirma import turnuva as tv
from tradebot.arastirma.panel import dengele_adim
from tradebot.canli.kollar import PaperKol
from tradebot.risk.motor import Durum, PortfoyIzleyici, RiskAyar
from tradebot.veri.depo import BarDepo


@dataclass
class KolDurum:
    """Bir kolun defterdeki durumu (kaynak: PostgreSQL paper defteri)."""
    ozkaynak: float
    nakit: float
    adet: dict[str, float] = field(default_factory=dict)
    onceki_h: dict[str, float] = field(default_factory=dict)
    ilk: bool = True
    izleyici: PortfoyIzleyici | None = None

    def isaretle(self, fiyat: dict[str, float]) -> float:
        """Piyasaya göre özkaynak (nakit + pozisyon değeri)."""
        self.ozkaynak = self.nakit + sum(a * fiyat[k] for k, a in self.adet.items() if a)
        return self.ozkaynak


@dataclass(frozen=True)
class Karar:
    kol: str
    bar_ms: int                 # kararın dayandığı son kapanmış barın AÇILIŞ zamanı
    kimlikler: tuple[str, ...]
    hedef: np.ndarray           # hedef_uret'in son satırı (sinyal × oynaklık ölçeği)
    etkin_hedef: np.ndarray     # fren/veto sonrası
    kaymis: np.ndarray          # mevcut ağırlık (son kapanışla)
    yeni: np.ndarray            # dengele_adim sonucu
    islem: np.ndarray           # işlem yapılacak enstrümanlar
    fiyat: np.ndarray           # son kapanış
    durum: str                  # normal | fren_* | acil_durdurma
    veto: tuple[str, ...]
    miktar: dict[str, float]    # emir miktarı (işaretli adet)


def izleyici_kur(kol: PaperKol, gecmis: list[tuple[int, float]]) -> PortfoyIzleyici | None:
    """Fren durumu özkaynak geçmişinden yeniden kurulur (yeniden başlatmada ayrı durum dosyası gerekmez).
    Araştırmadaki gibi acil durdurma kalıcı: paper'da kalıcı değil (kural 7 canlı parada; paper kolu gözlemdir)."""
    if not kol.ayar.frenler:
        return None
    iz = PortfoyIzleyici(RiskAyar(kaldirac=kol.ayar.kaldirac), baslangic_ms=gecmis[0][0] if gecmis else 0,
                         acil_kalici=False)  # özkaynak başlangıca oranla (1,0'dan), backtest gibi
    for t, oz in gecmis:
        iz.guncelle(oz / kol.baslangic_ozkaynak, t)
    return iz


def hazirla(depo: BarDepo, kayit: dict[str, dict], kol: PaperKol, bit_ms: int | None = None) -> tv.HazirGrup:
    return tv.grup_hazirla(depo, kayit, kol.grup, kol.zd, bit_ms=bit_ms)


def hedef_son(h: tv.HazirGrup, kol: PaperKol) -> np.ndarray:
    p = tv.cevir(kol.parametre, tv.bar_gun(kol.zd, h.takvim))
    return tv.hedef_uret(h, kol.strateji, p, kol.yon, kol.ayar, nedensellik=False)[-1]


def karar_ver(kol: PaperKol, h: tv.HazirGrup, d: KolDurum, vetolu: set[str]) -> Karar:
    """Son kapanmış bar için dengeleme kararı. `vetolu`: şu an geçerli vetolar (yalnız Jev'li kopya kullanır).
    Fren durumu, işlem yapılacak barın açılış anında güncellenir (backtest `calistir_panel` ile aynı an)."""
    g = h.g
    t_islem = int(g.t[-1]) + g.bar_ms
    ks = list(g.kimlikler)
    fiyat = g.kapanis[-1].copy()
    fsoz = dict(zip(ks, fiyat, strict=True))
    oz = d.isaretle(fsoz)
    kaymis = np.array([d.adet.get(k, 0.0) * fsoz[k] / oz if oz > 0 else 0.0 for k in ks])
    durum = Durum.NORMAL.value
    if d.izleyici is not None:
        durum = d.izleyici.guncelle(oz / kol.baslangic_ozkaynak, t_islem).value
    veto = np.array([kol.jev and k in vetolu for k in ks])
    hedef = hedef_son(h, kol)
    onceki = np.array([d.onceki_h.get(k, 0.0) for k in ks])
    yeni, etkin, islem = dengele_adim(hedef, kaymis, onceki, d.ilk, g.bar_var[-1] | g.bitti[-1], g.bitti[-1], durum,
                                      veto if veto.any() else None, kol.ayar.bant)
    miktar = {k: float((yeni[j] - kaymis[j]) * oz / fiyat[j]) for j, k in enumerate(ks) if islem[j] and fiyat[j] > 0
              and abs(yeni[j] - kaymis[j]) > 1e-12}
    return Karar(kol.ad, int(g.t[-1]), tuple(ks), hedef, etkin, kaymis, yeni, islem, fiyat, durum,
                 tuple(k for k, v in zip(ks, veto, strict=True) if v), miktar)
