"""Risk motoru, katman 1–4 (Final Doküman §Risk motoru). Emre giden tek yol `RiskMotoru.onayla`dır (değişmez kural 5).

Asimetri (değişmez kural 7): riski AZALTAN emir (mutlak pozisyonu küçülten) frende, acil durdurmada, vetoda ve kol
durdurmada da geçer; yalnız temel akıl kontrollerinden (fiyat bandı, geçerli miktar) geçmesi gerekir. Riski ARTIRAN
emir bütün katmanlardan geçmek zorundadır ve miktarı tavanlara göre küçültülebilir.

Portföy durumu (`PortfoyIzleyici`):
- günlük −%3 → `fren_gunluk` (yeni risk yok) → sonraki UTC gününde kendiliğinden kalkar
- haftalık −%8 → `fren_haftalik` → sonraki UTC haftasında (Pazartesi) kalkar
- tepeden −%25 → `acil_durdurma`: her şey kapatılır, KENDİLİĞİNDEN KALKMAZ; yalnız `acil_durdurma_kaldir` ile
  (Scryne'ın açık onayı; denetim izine yazılır). Bu fonksiyonu çağıran otomatik bir kod yolu yoktur.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from tradebot.cekirdek.boyut import KALDIRAC_TAVANI, kaldirac_dogrula

GUN = 86_400_000
HAFTA = 7 * GUN
PAZARTESI_KAYMA = 4 * GUN


class Durum(StrEnum):
    NORMAL = "normal"
    FREN_GUNLUK = "fren_gunluk"
    FREN_HAFTALIK = "fren_haftalik"
    ACIL_DURDURMA = "acil_durdurma"


@dataclass(frozen=True)
class RiskAyar:
    gunluk_fren: float = -0.03
    haftalik_fren: float = -0.08
    acil_durdurma: float = -0.25
    kaldirac: float = 1.0                 # portföy brüt maruziyet tavanı (≤ 3, kaldirac_dogrula)
    enstruman_tavani: float = 0.5         # tek enstrümanın özkaynağa oranı (brüt)
    sinif_tavani: float = 1.0             # tek varlık sınıfının oranı
    azami_emir_orani: float = 0.5         # tek emrin notional / özkaynak
    fiyat_bandi: float = 0.05             # emir fiyat tahmini son fiyattan en çok bu kadar sapabilir
    bayat_bar_sayisi: float = 2.0         # son bar yaşı > 2 periyot → veri bayat
    dakikalik_emir_sayisi: int = 30
    likidasyon_mesafesi_kat: float = 3.0  # kaldıraçlı pozisyonda likidasyona uzaklık ≥ 3 × günlük oynaklık

    def __post_init__(self) -> None:
        kaldirac_dogrula(self.kaldirac)


@dataclass(frozen=True)
class EmirIstegi:
    kimlik: str               # enstrüman
    sinif: str
    miktar: float             # işaretli (+ alış, − satış), adet
    fiyat_tahmini: float
    kol: str
    zaman_ms: int
    istemci_emir_id: str


@dataclass(frozen=True)
class Piyasa:
    son_fiyat: float
    son_bar_ms: int
    bar_ms: int
    acik: bool
    adim_miktar: float = 0.0          # lot adımı (0 = yuvarlama yok)
    gunluk_oynaklik: float | None = None
    likidasyon_fiyati: float | None = None


@dataclass
class Portfoy:
    ozkaynak: float
    pozisyonlar: dict[str, float] = field(default_factory=dict)  # kimlik → adet
    fiyatlar: dict[str, float] = field(default_factory=dict)     # kimlik → son fiyat
    siniflar: dict[str, str] = field(default_factory=dict)       # kimlik → sınıf
    durum: Durum = Durum.NORMAL
    durdurulan_kollar: set[str] = field(default_factory=set)
    veto: set[str] = field(default_factory=set)                   # Jev/haber vetosu: bu enstrümanlarda risk artırılamaz

    def notional(self, kimlik: str, adet: float | None = None) -> float:
        a = self.pozisyonlar.get(kimlik, 0.0) if adet is None else adet
        return a * self.fiyatlar.get(kimlik, 0.0)

    def brut(self, haric: str | None = None) -> float:
        return sum(abs(self.notional(k)) for k in self.pozisyonlar if k != haric)


@dataclass(frozen=True)
class Karar:
    onay: bool
    miktar: float
    gerekceler: tuple[str, ...]
    risk_azaltan: bool


class RiskMotoru:
    def __init__(self, ayar: RiskAyar | None = None) -> None:
        self.ayar = ayar or RiskAyar()
        self._emir_zamanlari: list[int] = []
        self._goruldu: set[str] = set()

    def onayla(self, e: EmirIstegi, p: Piyasa, pf: Portfoy) -> Karar:
        a, ger = self.ayar, []
        mevcut = pf.pozisyonlar.get(e.kimlik, 0.0)
        yeni = mevcut + e.miktar
        azaltan = abs(yeni) < abs(mevcut) and (yeni == 0 or (yeni > 0) == (mevcut > 0))

        # --- Katman 1: temel akıl kontrolleri (azaltan emirler dahil) ---
        if not (e.miktar and e.fiyat_tahmini > 0 and p.son_fiyat > 0):
            return Karar(False, 0.0, ("geçersiz miktar ya da fiyat",), azaltan)
        if e.istemci_emir_id in self._goruldu:
            return Karar(False, 0.0, ("çift emir (aynı istemci emir kimliği)",), azaltan)
        if abs(e.fiyat_tahmini / p.son_fiyat - 1) > a.fiyat_bandi:
            return Karar(False, 0.0, (f"fiyat bandı dışı (±%{a.fiyat_bandi * 100:g})",), azaltan)
        if azaltan:
            self._kaydet(e)
            return Karar(True, e.miktar, ("riski azaltan emir",), True)

        # --- Katman 1 (risk artıran) ---
        if not p.acik:
            ger.append("piyasa kapalı")
        if e.zaman_ms - p.son_bar_ms > a.bayat_bar_sayisi * p.bar_ms:
            ger.append("veri bayat")
        if e.kimlik in pf.veto:
            ger.append("veto: bu enstrümanda risk artırılamaz")
        son_dk = [z for z in self._emir_zamanlari if e.zaman_ms - z < 60_000]
        if len(son_dk) >= a.dakikalik_emir_sayisi:
            ger.append("emir hızı sınırı")
        # --- Katman 3: kol ---
        if e.kol in pf.durdurulan_kollar:
            ger.append(f"kol durduruldu: {e.kol}")
        # --- Katman 4: portföy durumu ---
        if pf.durum != Durum.NORMAL:
            ger.append(f"portföy durumu: {pf.durum.value}")
        if ger:
            return Karar(False, 0.0, tuple(ger), False)

        # --- Miktar tavanları (katman 1, 2, 4): küçültülebilir ---
        oz = pf.ozkaynak
        izinli_ek = abs(e.miktar)
        birim = e.fiyat_tahmini
        izinli_ek = min(izinli_ek, a.azami_emir_orani * oz / birim)
        enst_kalan = a.enstruman_tavani * oz - abs(mevcut) * birim
        izinli_ek = min(izinli_ek, max(enst_kalan, 0.0) / birim)
        sinif_brut = sum(abs(pf.notional(k)) for k, s in pf.siniflar.items() if s == e.sinif)
        izinli_ek = min(izinli_ek, max(a.sinif_tavani * oz - sinif_brut, 0.0) / birim)
        kaldirac_kalan = min(a.kaldirac, KALDIRAC_TAVANI) * oz - pf.brut()
        izinli_ek = min(izinli_ek, max(kaldirac_kalan, 0.0) / birim)
        # --- Katman 2: likidasyon mesafesi (kaldıraçlı pozisyonlarda) ---
        if p.likidasyon_fiyati and p.gunluk_oynaklik:
            mesafe = abs(p.son_fiyat / p.likidasyon_fiyati - 1)
            if mesafe < a.likidasyon_mesafesi_kat * p.gunluk_oynaklik:
                return Karar(False, 0.0, (f"likidasyona çok yakın ({mesafe:.1%} < {a.likidasyon_mesafesi_kat:g}σ)",), False)
        if p.adim_miktar > 0:  # lot adımına AŞAĞI yuvarla; 1/0,00001 = 99999,999… gibi kayan nokta hatasına tolerans
            izinli_ek = round(math.floor(izinli_ek / p.adim_miktar + 1e-9) * p.adim_miktar, 12)
        if izinli_ek <= 0:
            return Karar(False, 0.0, ("tavan dolu (enstrüman/sınıf/kaldıraç/emir boyutu)",), False)
        miktar = izinli_ek if e.miktar > 0 else -izinli_ek
        if abs(miktar) < abs(e.miktar):
            ger.append(f"miktar tavana göre küçültüldü ({abs(e.miktar):g} → {abs(miktar):g})")
        self._kaydet(e)
        return Karar(True, miktar, tuple(ger) or ("onay",), False)

    def _kaydet(self, e: EmirIstegi) -> None:
        self._goruldu.add(e.istemci_emir_id)
        self._emir_zamanlari = [z for z in self._emir_zamanlari if e.zaman_ms - z < 60_000] + [e.zaman_ms]


class PortfoyIzleyici:
    """Özkaynak yolundan fren ve acil durdurma durumunu türetir (UTC gün/hafta)."""

    def __init__(self, ayar: RiskAyar | None = None, baslangic_ozkaynak: float = 1.0, baslangic_ms: int = 0,
                 acil_kalici: bool = True) -> None:
        """`acil_kalici=False` YALNIZ araştırma içindir: acil durdurma olay olarak sayılır (`acil_sayisi`) ama durum
        kalıcı olmaz; stratejinin tüm dönemi ölçülür ve acil tetikleyen strateji kapıdan geçemez (tarama). Canlıda
        her zaman True: acil durdurma yalnız Scryne'ın onayıyla kalkar."""
        self.ayar = ayar or RiskAyar()
        self.acil_kalici = acil_kalici
        self.acil_sayisi = 0
        self.tepe = baslangic_ozkaynak
        self.gun, self.hafta = self._gun(baslangic_ms), self._hafta(baslangic_ms)
        self.gun_bas = self.hafta_bas = self.son = baslangic_ozkaynak
        self.durum = Durum.NORMAL

    @staticmethod
    def _gun(t: int) -> int:
        return t // GUN

    @staticmethod
    def _hafta(t: int) -> int:
        return (t - PAZARTESI_KAYMA) // HAFTA

    def guncelle(self, ozkaynak: float, t_ms: int) -> Durum:
        g, h = self._gun(t_ms), self._hafta(t_ms)
        if g != self.gun:  # yeni UTC günü: günlük fren kalkar, referans yenilenir
            self.gun, self.gun_bas = g, ozkaynak
            if self.durum == Durum.FREN_GUNLUK:
                self.durum = Durum.NORMAL
        if h != self.hafta:
            self.hafta, self.hafta_bas = h, ozkaynak
            if self.durum == Durum.FREN_HAFTALIK:
                self.durum = Durum.NORMAL
        self.tepe = max(self.tepe, ozkaynak)
        self.son = ozkaynak
        if self.durum == Durum.ACIL_DURDURMA:
            return self.durum  # kendiliğinden kalkmaz
        a = self.ayar
        if ozkaynak / self.tepe - 1 <= a.acil_durdurma:
            self.acil_sayisi += 1
            if not self.acil_kalici:  # araştırma: olay kaydı + tepe yenilenir (inceleme sonrası devam varsayımı)
                self.tepe = ozkaynak
                self.durum = Durum.FREN_HAFTALIK
                return Durum.ACIL_DURDURMA
            self.durum = Durum.ACIL_DURDURMA
        elif ozkaynak / self.hafta_bas - 1 <= a.haftalik_fren:
            self.durum = Durum.FREN_HAFTALIK
        elif ozkaynak / self.gun_bas - 1 <= a.gunluk_fren and self.durum == Durum.NORMAL:
            self.durum = Durum.FREN_GUNLUK
        return self.durum

    def acil_durdurma_kaldir(self, onaylayan: str, gerekce: str, denetim_kaydet=None) -> None:
        """YALNIZ Scryne'ın açık onayıyla (CLI/Telegram onay adımı). `denetim_kaydet(bilesen, olay, veri)` verilirse iz."""
        if self.durum != Durum.ACIL_DURDURMA:
            raise RuntimeError("acil durdurma aktif değil")
        if not onaylayan.strip() or not gerekce.strip():
            raise ValueError("onaylayan ve gerekçe zorunlu")
        if denetim_kaydet is not None:
            denetim_kaydet("risk", "acil_durdurma_kaldirildi",
                           {"onaylayan": onaylayan, "gerekce": gerekce, "eski_tepe": self.tepe, "ozkaynak": self.son})
        # Tepe güncel özkaynağa çekilir; yoksa eski tepeye göre hemen yeniden acil durdurma olurdu.
        self.tepe = self.gun_bas = self.hafta_bas = self.son
        self.durum = Durum.NORMAL
