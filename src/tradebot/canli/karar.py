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
from tradebot.canli.kollar import PORTFOY, PaperKol
from tradebot.risk.motor import Durum, PortfoyIzleyici, RiskAyar
from tradebot.veri.depo import BarDepo
from tradebot.veri.takvim import ZAMAN_DILIMI_MS


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


def izleyici_kur(kol: PaperKol, gecmis: list[tuple[int, float]],
                 kaldirmalar: list[tuple[int, str, str]] = ()) -> PortfoyIzleyici | None:
    """Fren durumu özkaynak geçmişinden yeniden kurulur (yeniden başlatmada ayrı durum dosyası gerekmez).

    Gözlem kollarında acil durdurma kalıcı değildir (araştırmadaki gibi): kolun stratejisi ölçülür. Portföy kolu gerçek
    hesabın paper karşılığıdır: orada kalıcıdır (kural 7) ve yalnız onaylı `acil_kaldir` olayıyla kalkar.
    `kaldirmalar` (zaman_ms, onaylayan, gerekce) özkaynak geçmişiyle aynı zaman sırasında yeniden oynatılır."""
    if not kol.ayar.frenler:
        return None
    iz = PortfoyIzleyici(RiskAyar(kaldirac=kol.ayar.kaldirac), baslangic_ms=gecmis[0][0] if gecmis else 0,
                         acil_kalici=kol.strateji == PORTFOY)  # özkaynak başlangıca oranla (1,0'dan), backtest gibi
    kalan = sorted(kaldirmalar)

    def uygula(t: int | None) -> None:
        while kalan and (t is None or kalan[0][0] <= t):
            _, kim, neden = kalan.pop(0)
            if iz.durum == Durum.ACIL_DURDURMA:
                iz.acil_durdurma_kaldir(kim, neden)

    for t, oz in gecmis:
        uygula(t)
        iz.guncelle(oz / kol.baslangic_ozkaynak, t)
    uygula(None)
    return iz


def hazirla(depo: BarDepo, kayit: dict[str, dict], kol: PaperKol, bit_ms: int | None = None) -> tv.HazirGrup:
    return tv.grup_hazirla(depo, kayit, kol.grup, kol.zd, bit_ms=bit_ms)


def hedef_son(h: tv.HazirGrup, kol: PaperKol) -> np.ndarray:
    p = tv.cevir(kol.parametre, tv.bar_gun(kol.zd, h.takvim))
    return tv.hedef_uret(h, kol.strateji, p, kol.yon, kol.ayar, nedensellik=False)[-1]


def agresif_hedef(depo: BarDepo, kayit: dict[str, dict], kol: PaperKol, kaynaklar: list[PaperKol],
                  kapanis_ms: int) -> np.ndarray:
    """Agresif gözlem kolu: kaynak kolların güncel hedeflerinin (her biri kendi son tamamlanmış sınırında) ortalaması ×
    tam Kelly, enstrüman tavanıyla kırpılır (spot: yalnız long). Brüt tavanı risk motoru uygular."""
    hedefler, ks = [], None
    for k in kaynaklar:
        zd_ms = ZAMAN_DILIMI_MS[k.zd]
        h = hazirla(depo, kayit, k, bit_ms=kapanis_ms - kapanis_ms % zd_ms)
        if ks is None:
            ks = list(h.g.kimlikler)
        elif list(h.g.kimlikler) != ks:
            raise ValueError("agresif kolun kaynakları aynı enstrümanları taşımalı")
        hedefler.append(np.nan_to_num(hedef_son(h, k)))
    tavan = RiskAyar(kaldirac=kol.ayar.kaldirac).enstruman_tavani
    return np.clip(np.mean(hedefler, axis=0) * kol.parametre["kelly_carpani"], -tavan if kol.yon == "long_short" else 0.0,
                   tavan)


def karar_ver(kol: PaperKol, h: tv.HazirGrup, d: KolDurum, vetolu: set[str], hedef: np.ndarray | None = None) -> Karar:
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
    hedef = hedef_son(h, kol) if hedef is None else np.asarray(hedef, dtype=float)
    onceki = np.array([d.onceki_h.get(k, 0.0) for k in ks])
    yeni, etkin, islem = dengele_adim(hedef, kaymis, onceki, d.ilk, g.bar_var[-1] | g.bitti[-1], g.bitti[-1], durum,
                                      veto if veto.any() else None, kol.ayar.bant)
    miktar = {k: float((yeni[j] - kaymis[j]) * oz / fiyat[j]) for j, k in enumerate(ks) if islem[j] and fiyat[j] > 0
              and abs(yeni[j] - kaymis[j]) > 1e-12}
    return Karar(kol.ad, int(g.t[-1]), tuple(ks), hedef, etkin, kaymis, yeni, islem, fiyat, durum,
                 tuple(k for k, v in zip(ks, veto, strict=True) if v), miktar)
