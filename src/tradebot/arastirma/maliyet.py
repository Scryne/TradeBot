"""Piyasa başına maliyet modeli (değişmez kural 4: maliyet hep aleyhte; belirsizlikte kötü yöne yuvarla).

Taraf başı maliyet (bps) = ücret × (1 + ücret vergisi) + yarım spread + kayma. Spread verisi varsa (Dukascopy) bardaki
spread kullanılır, yoksa varsayılan yarım spread. CFD/marjin pozisyonları elde tutulduğu süre için yıllık finansman
öder (uzun ya da kısa fark etmeksizin aleyhte). Spot pozisyonlar finansman ödemez.

Varsayımlar (2026-09; paper aşamasında gerçek dolumlarla ölçülüp güncellenir, Faz 11):
- Binance spot: VIP0 taker %0,10 (BNB indirimi yok), yarım spread 1 bps, kayma 2 bps (büyük coinler; küçükler için
  likiditeye bağlı ek Faz 5'te).
- Dukascopy (FX/CFD): komisyon 0,5 bps (doğrulanmamış, kötü yönde tahmin), spread veriden, kayma 0,5 bps; finansman
  yıllık FX %2, metal %4, emtia %4, endeks %6 (≈ gösterge faiz + aracı kurum payı).
- ABD ETF: komisyon 1 bps, yarım spread 1 bps, kayma 1 bps; açığa satışta yıllık %1 ödünç maliyeti.
- Nasdaq-100 hisseleri: ücret 0,5 bps (SEC/TAF/CAT, komisyon 0), yarım spread 2 bps, kayma 3 bps (açılış dolumu).
- BIST hisse: komisyon 4 bps + BSMV (%5), yarım spread 5 bps, kayma 5 bps.
- VİOP (NCM): komisyon 2 bps + BSMV (%5). Spike 08 demo işleminde (2026-09-28) F_USDTRY 1 kontrat, taraf başı
  7,91 TL = 1,5 bps + BSMV; gerçek hesap sözleşmesi ve borsa/takas payları için 0,5 bps pay bırakıldı.
  - Endeks vadeli: yarım spread 2 bps (1 dk barlarda medyan ~0,3, p90 ~1,9; canlı tikte tam spread medyan 1,9 bps),
    kayma 2 bps. Vade devri: yılda 6 geçiş × 2 taraf × ~10 bps ≈ yıllık %1,2 (elde tutma süresine orantılı, finansman
    alanıyla). Faiz farkı sürekli serinin kendisinde (baz erimesi), ayrıca finansman yok.
  - USDTRY vadeli: yarım spread 1 bps (canlı tikte tam spread medyan 0,6, p90 0,8), kayma 1 bps, aylık devir ≈ yıllık %1,5.
- NCM forex hesabı (NCMFX, 2026-09-28 spike 08): GOLD demo işleminde komisyon 0, maliyet spread'in içinde; dolum
  kotasyon fiyatından (kayma 0, 16 ms). Demo dolumu gerçekten iyimser olabilir: kayma 1 bps. Spread veriden (MT5 barı).
  Canlı tik tam spread medyanları (Pazartesi 07:00 UTC, 10 dk): EURUSD 1,8, GBPUSD 1,5, USDJPY 1,3, GOLD 1,7,
  SILVER 10,6, ES 0,8, NQ 0,5, GER40 1,0, CL 2,1 bps.
  - Swap (günlük, nokta): GOLD uzun −58 / kısa +22 ≈ yıllık %5,1 / +%1,9; SILVER uzun −10 / kısa −30 ≈ %6,0 / %17,9.
    Model: metal finansman %6, kısada ek %12 (altın kısada fazla ödetir, aleyhte). FX majörlerde demo swap 0
    (gerçek hesapta doğrulanmadı): %2 korunur.
  - Endeks ve petrol işlemi vadeli kontratta (ES6Z, CL6X…): swap yok, komisyon ölçülmedi (0,5 bps aleyhte), devir
    maliyeti finansman alanında.
"""
from __future__ import annotations

from dataclasses import dataclass

YIL_MS = 365.25 * 86_400_000


@dataclass(frozen=True)
class MaliyetModeli:
    ad: str
    ucret_bps: float
    yari_spread_bps: float
    kayma_bps: float
    finansman_yillik: float = 0.0
    ucret_vergisi: float = 0.0
    spread_veriden: bool = False
    aciga_satis_yillik: float = 0.0  # kısa pozisyonun ek yıllık maliyeti (ödünç alma; finansmana eklenir)

    def taraf_bps(self, yari_spread_bps: float | None = None) -> float:
        ys = self.yari_spread_bps if yari_spread_bps is None else yari_spread_bps
        return self.ucret_bps * (1 + self.ucret_vergisi) + ys + self.kayma_bps


MODELLER = {
    "BINANCE": MaliyetModeli("binance_spot", ucret_bps=10.0, yari_spread_bps=1.0, kayma_bps=2.0),
    "DUKASCOPY:fx": MaliyetModeli("cfd_fx", 0.5, 0.5, 0.5, finansman_yillik=0.02, spread_veriden=True),
    "DUKASCOPY:metal": MaliyetModeli("cfd_metal", 0.5, 1.0, 0.5, finansman_yillik=0.04, spread_veriden=True),
    "DUKASCOPY:emtia": MaliyetModeli("cfd_emtia", 0.5, 1.5, 0.5, finansman_yillik=0.04, spread_veriden=True),
    "DUKASCOPY:endeks": MaliyetModeli("cfd_endeks", 0.5, 0.5, 0.5, finansman_yillik=0.06, spread_veriden=True),
    "ARCA": MaliyetModeli("abd_etf", 1.0, 1.0, 1.0, aciga_satis_yillik=0.01),
    # Nasdaq-100 hisseleri (2026-10-18, Alpaca nakit hesabı): komisyon 0; düzenleyici ücretler satışta (SEC 20,6 $/milyon
    # ≈ 0,21 bps, FINRA TAF hisse başı ≤ 8,30 $, CAT) → taraf başı 0,5 bps (aleyhte yuvarlandı). Yarım spread 2 bps
    # (büyük hisselerde kotasyon spread'i ~1–3 bps). Kayma 3 bps: dolum açılışta (OPG / ilk dakika), açılış spread'i gün
    # içinden geniş; Alpaca paper OPG'yi müzayede fiyatıyla değil anlık bid/ask'tan dolduruyor (2021 ölçümü 12–43 bps
    # sapma, docs/turnuva/Dalga-19-Nasdaq.md). Gidiş-dönüş 11 bps. Açığa satış yıllık %1 (kollar yalnız uzun).
    "NASDAQ:hisse": MaliyetModeli("nasdaq_hisse", 0.5, 2.0, 3.0, aciga_satis_yillik=0.01),
    # Gün içi QQQ (dalga 20; veri Dukascopy Nasdaq 100 CFD saatlik, uygulama Alpaca'da QQQ): QQQ kotasyon spread'i
    # ~1 sent (~0,2 bps) → yarım spread 0,5 bps (aleyhte), kayma 1,2 bps (seans içi piyasa emri), ücret 0,3 bps (satışta
    # SEC/TAF) → taraf başı 2 bps, gidiş-dönüş 4 bps. Pozisyon gece taşınmaz: finansman yok. Kısa: ödünç %1/yıl.
    "ABD:qqq_gun_ici": MaliyetModeli("qqq_gun_ici", 0.3, 0.5, 1.2, aciga_satis_yillik=0.01),
    "BIST:hisse": MaliyetModeli("bist_hisse", 4.0, 5.0, 5.0, ucret_vergisi=0.05),
    "BIST:endeks": MaliyetModeli("bist_endeks_vadeli_vekil", 2.0, 2.0, 2.0),  # endeks doğrudan alınamaz; VİOP vekili
    "VIOP:endeks_vadeli": MaliyetModeli("viop_endeks", 2.0, 2.0, 2.0, finansman_yillik=0.012, ucret_vergisi=0.05),
    # USDTRY vadeli: 1 dk barlarda tam spread medyan ~0,6 bps, p90 ~1,8 (yarım 1 bps aleyhte); aylık devir: 12 × 2 taraf
    # × ~6 bps ≈ yıllık %1,5. Komisyon ölçüldü (spike 08): 1,5 bps + BSMV, 2 bps'e yuvarlandı.
    "VIOP:doviz_vadeli": MaliyetModeli("viop_doviz", 2.0, 1.0, 1.0, finansman_yillik=0.015, ucret_vergisi=0.05),
    # ham yakın vade (XU30_YAKINVADE) endeks vadelisiyle aynı kontrattır
    "VIOP:endeks": MaliyetModeli("viop_endeks", 2.0, 2.0, 2.0, finansman_yillik=0.012, ucret_vergisi=0.05),
    # altın vadelileri (spike 08 canlı tik, tam spread medyan / p90): F_XAUUSD 2,6 / 2,9 bps, F_XAUTRYM 3,8 / 6,2 bps.
    # İki ayda bir devir: 6 × 2 taraf × ~(yarım spread + kayma + komisyon)
    "VIOP:altin_usd": MaliyetModeli("viop_altin_usd", 2.0, 1.5, 1.5, finansman_yillik=0.01, ucret_vergisi=0.05),
    "VIOP:altin_try": MaliyetModeli("viop_altin_try", 2.0, 2.5, 2.0, finansman_yillik=0.012, ucret_vergisi=0.05),
    # NCM forex hesabı (spike 08): komisyon 0 (GOLD ölçüldü), spread MT5 barından; vadeli CFD'lerde komisyon ölçülmedi
    "NCMFX:fx": MaliyetModeli("ncm_fx", 0.0, 1.0, 1.0, finansman_yillik=0.02, spread_veriden=True),
    # Dalga 10 (gün içi/olay döviz kolları, Dukascopy verisiyle NCM'de uygulanacak): veri spread'i (Dukascopy, yarım
    # ~0,2–0,5 bps) NCM'den dar olduğu için kullanılmaz; NCM canlı tik tam spread medyanı 1,3–1,8 bps → yarım 1 bps
    # (aleyhte yuvarlandı) + kayma 1 bps = taraf başı 2 bps, gidiş-dönüş 4 bps. Finansman %2 (tutulan süreye orantılı).
    "NCMFX:fx_sabit": MaliyetModeli("ncm_fx_sabit", 0.0, 1.0, 1.0, finansman_yillik=0.02),
    # Dalga 11 (ABD endeksi, Dukascopy spot verisiyle NCM endeks vadeli CFD'sinde uygulanacak; ES/NQ canlı tik tam spread
    # medyanı 0,8 / 0,5 bps): komisyon 0,5 (ölçülmedi), yarım spread 0,5, kayma 1 → taraf başı 2 bps. Vadeli getirisi
    # ≈ spot − (faiz − temettü): tutulan süre için yıllık %5 finansman (T-bill üst sınırı, temettü yok sayılır; aleyhte).
    "NCMFX:endeks_sabit": MaliyetModeli("ncm_endeks_sabit", 0.5, 0.5, 1.0, finansman_yillik=0.05),
    "NCMFX:metal": MaliyetModeli("ncm_metal", 0.0, 1.0, 1.0, finansman_yillik=0.06, spread_veriden=True,
                                 aciga_satis_yillik=0.12),
    # Dalga 3 türetilmiş vadeli serileri (veri/vadeli.py; getiri zaten nakit üstü). Uygulama NCM'de: endeks vadeli CFD'si
    # (ES6Z…, çeyreklik devir), metal ve döviz spot CFD'si (swap ≈ faiz farkı + kurum payı). Finansman alanı yalnız
    # kurum payını taşır: döviz %1, metal %1,5 (GOLD swap'ı 2026-09-28: uzun −%5,1, kısa +%1,9; adil fark ~±%4,3).
    "VADELI:endeks": MaliyetModeli("vadeli_endeks", 0.5, 0.5, 1.0, finansman_yillik=0.005),
    "VADELI:fx": MaliyetModeli("vadeli_fx", 0.0, 1.0, 1.0, finansman_yillik=0.01),
    "VADELI:metal": MaliyetModeli("vadeli_metal", 0.0, 1.0, 1.0, finansman_yillik=0.015),
    # vadeli: çeyreklik devir 4 × 2 taraf × ~1,5 bps ≈ %0,1; sürekli seri ayarı doğrulanana kadar %0,5 (dalga 3)
    "NCMFX:endeks": MaliyetModeli("ncm_endeks_vadeli", 0.5, 0.5, 1.0, finansman_yillik=0.005, spread_veriden=True),
    # petrol vadelisi aylık devreder: 12 × 2 × ~2 bps ≈ %0,5; aleyhte %1
    "NCMFX:emtia": MaliyetModeli("ncm_emtia_vadeli", 0.5, 1.5, 1.0, finansman_yillik=0.01, spread_veriden=True),
}


def model(piyasa: str, sinif: str) -> MaliyetModeli:
    for anahtar in (f"{piyasa}:{sinif}", piyasa):
        if anahtar in MODELLER:
            return MODELLER[anahtar]
    raise KeyError(f"maliyet modeli yok: {piyasa}/{sinif}")
