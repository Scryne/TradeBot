"""Kol (çok enstrümanlı portföy) backtest'i ve grup verisinin hazırlanması (Faz 5).

Kol = strateji × piyasa grubu × zaman dilimi. Grup barları ortak zaman ızgarasına dizilir (bar açılışlarının
birleşimi). Enstrümanın o anda barı yoksa fiyatı ileri doldurulur (getiri 0) ve o anda işlem yapılamaz.

Zaman kuralı `backtest.calistir` ile aynı: hedef[t] bar t'nin kapanışında verilir, bar t+1'in açılışında dolar.
Tek enstrümanlı grup, `backtest.calistir` ile birebir aynı sonucu verir (tests/test_panel.py).

Point-in-time evren: gün d'nin evren satırı yalnız d dahil geçmiş günlerin barlarından hesaplanır. Bar t için
kullanılan satır, bar t kapanmadan önce TAMAMEN bitmiş son gündür: gün = (t + bar_ms) // GÜN − 1.

Kalkan (işlemi biten) enstrüman: son gerçek barından sonra pozisyon zorla kapatılır, maliyet 3 kat (aleyhte; kural 4).
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

import numpy as np
import polars as pl

from tradebot.arastirma.backtest import Sonuc
from tradebot.arastirma.maliyet import YIL_MS, MaliyetModeli
from tradebot.cekirdek import Barlar
from tradebot.veri.depo import BarDepo, turet
from tradebot.veri.takvim import ZAMAN_DILIMI_MS

GUN = 86_400_000
KALKAN_MALIYET_CARPANI = 3.0

# Kripto evreninden kural olarak dışlananlar (önceden yazılı; config/turnuva/dalga1.yaml da bunu kullanır)
KRIPTO_DISLA_DESEN = re.compile(r"^BINANCE:.*(UP|DOWN|BULL|BEAR)USDT$")
KRIPTO_DISLA = {  # stabil, itibari para, sarılı/kopya varlıklar
    "USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDD", "AEUR", "EUR", "GBP", "AUD", "TRY", "BRL", "BFUSD",
    "BKRW", "SUSD", "UST", "PYUSD", "XUSD", "USD1", "RLUSD", "EURI", "BIDR", "IDRT", "UAH", "NGN", "ZAR", "RUB",
    "USDS", "USDE", "PAXG", "XAUT", "WBTC", "WBETH", "BETH", "BNSOL", "BULL", "BEAR",
}


def kripto_dislanir_mi(kimlik: str) -> bool:
    if KRIPTO_DISLA_DESEN.match(kimlik):
        return True
    taban = kimlik.removeprefix("BINANCE:").removesuffix("USDT")
    return taban in KRIPTO_DISLA


@dataclass(frozen=True)
class GrupVerisi:
    kimlikler: list[str]
    t: np.ndarray            # ortak ızgara (bar açılışları)
    acilis: np.ndarray       # [n, k] yürütme fiyatı, ileri doldurulmuş
    kapanis: np.ndarray      # [n, k] ileri doldurulmuş
    bar_var: np.ndarray      # [n, k] o anda gerçek bar var mı (işlem yapılabilir)
    bitti: np.ndarray        # [n, k] son gerçek bardan sonrası
    yari_spread_bps: np.ndarray | None  # [n, k] veriden (Dukascopy) ya da None
    barlar: list[Barlar]     # her enstrümanın kendi barları (gösterge hesabı için)
    konum: list[np.ndarray]  # barlar[j]'nin ızgaradaki indeksleri
    veri_hash: str
    bar_ms: int
    ciro: list[np.ndarray] | None = None  # her enstrümanın bar cirosu (kapanış × hacim), temettü düzeltmesinden ÖNCE


def bar_yukle(depo: BarDepo, kimlik: str, zd: str) -> tuple[pl.DataFrame, str] | None:
    """İstenen zaman dilimi yoksa en yakın alt zaman diliminden türetir. (df, dosya sha256) ya da None."""
    for kaynak_zd in [zd] + [z for z in ("1h", "1m") if ZAMAN_DILIMI_MS[z] < ZAMAN_DILIMI_MS[zd]]:
        yol = depo.yol(kimlik, kaynak_zd)
        if yol.exists():
            df = depo.oku(kimlik, kaynak_zd)
            if kaynak_zd != zd:
                df = turet(df, ZAMAN_DILIMI_MS[zd]).sort("acilis_ms")
            return df, hashlib.sha256(yol.read_bytes()).hexdigest()
    return None


def grup_yukle(depo: BarDepo, kimlikler: list[str], zd: str, bas_ms: int | None = None,
               bit_ms: int | None = None) -> GrupVerisi:
    """`bit_ms`: bu andan (dahil değil) sonra AÇILAN barlar kullanılmaz."""
    dfs, hashler, adlar = [], [], []
    for k in kimlikler:
        r = bar_yukle(depo, k, zd)
        if r is None or r[0].is_empty():
            continue
        df = r[0]
        if bas_ms is not None:
            df = df.filter(pl.col("acilis_ms") >= bas_ms)
        if bit_ms is not None:
            df = df.filter(pl.col("acilis_ms") < bit_ms)
        # Ciro temettü düzeltmesinden önce: `adj_close / close` çarpanı SONRAKİ temettülere bağlıdır, point-in-time
        # likidite sıralamasına gelecek bilgisi sokardı (2026-09-28 denetimi). Yahoo close'u yalnız bölünme düzeltmeli,
        # hacmi de öyle: çarpımı gerçek ciro.
        df = toplam_getiri(df.with_columns((pl.col("close") * pl.col("volume")).alias("_ciro")))
        if len(df) < 3:
            continue
        dfs.append(df)
        hashler.append(f"{k}:{r[1]}")
        adlar.append(k)
    if not dfs:
        raise FileNotFoundError(f"grup için bar yok ({zd}): {kimlikler[:5]}…")
    t = np.unique(np.concatenate([d["acilis_ms"].to_numpy() for d in dfs]))
    n, k = len(t), len(dfs)
    acilis, kapanis = np.full((n, k), np.nan), np.full((n, k), np.nan)
    ys = np.full((n, k), np.nan)
    bar_var, bitti = np.zeros((n, k), dtype=bool), np.zeros((n, k), dtype=bool)
    barlar, konum, ciro = [], [], []
    spread_var = False
    for j, d in enumerate(dfs):
        ix = np.searchsorted(t, d["acilis_ms"].to_numpy())
        o = d["open"].to_numpy()
        acilis[ix, j], kapanis[ix, j], bar_var[ix, j] = o, d["close"].to_numpy(), True
        if "spread" in d.columns:
            ys[ix, j] = d["spread"].to_numpy() / 2 / o * 1e4
            spread_var = True
        bitti[ix[-1] + 1:, j] = True
        barlar.append(Barlar.sozlukten({"t": d["acilis_ms"], "open": d["open"], "high": d["high"], "low": d["low"],
                                        "close": d["close"], "volume": d["volume"]}))
        konum.append(ix)
        ciro.append(d["_ciro"].to_numpy())
    acilis, kapanis = _ileri_doldur(acilis), _ileri_doldur(kapanis)
    return GrupVerisi(adlar, t, acilis, kapanis, bar_var, bitti, ys if spread_var else None, barlar, konum,
                      hashlib.sha256("|".join(hashler).encode()).hexdigest(), ZAMAN_DILIMI_MS[zd], ciro)


def toplam_getiri(df: pl.DataFrame) -> pl.DataFrame:
    """`adj_close` varsa (Yahoo: bölünme + temettü düzeltmeli) OHLC'yi aynı günün `adj_close / close` çarpanıyla ölçekler:
    getiri temettü dahil ölçülür (long temettüyü alır, short öder). Çarpan yalnız o günden SONRAKİ temettülere bağlı
    sabittir; iki geçmiş gün arasındaki oran yalnız aralarındaki temettülere bağlıdır → oran tabanlı göstergeler
    nedensel kalır. `adj_close` eksikse çarpan önceki günden taşınır."""
    if "adj_close" not in df.columns:
        return df
    k = (pl.col("adj_close") / pl.col("close")).fill_nan(None).forward_fill().backward_fill().fill_null(1.0)
    return df.with_columns(k.alias("_k")).with_columns(
        *(pl.col(c) * pl.col("_k") for c in ("open", "high", "low", "close"))).drop("_k")


def kur_cevir(g: GrupVerisi, depo: BarDepo, kur_kimlik: str) -> GrupVerisi:
    """Yerel para fiyatlarını (ör. TRY) kur serisiyle (ör. USDTRY) USD'ye çevirir: fiyat_usd = fiyat / kur. Kur, barın
    açılışından önceki son kur barının kapanışıdır (nedensel). Sinyaller yerel fiyattan (g.barlar) üretilmeye devam
    eder; getiri, oynaklık ve maliyet USD fiyatla ölçülür (sermaye USD, pozisyon kur riskini de taşır)."""
    r = bar_yukle(depo, kur_kimlik, "1h") or bar_yukle(depo, kur_kimlik, "1d")
    if r is None:
        raise FileNotFoundError(f"kur serisi yok: {kur_kimlik}")
    kdf, kh = r
    kt = kdf["acilis_ms"].to_numpy() + (int(np.median(np.diff(kdf["acilis_ms"].to_numpy()))) if len(kdf) > 1 else 0)
    kc = kdf["close"].to_numpy()
    i = np.searchsorted(kt, g.t, side="right") - 1  # açılıştan önce kapanmış son kur barı
    kur = np.where(i >= 0, kc[np.maximum(i, 0)], np.nan)[:, None]
    return GrupVerisi(g.kimlikler, g.t, g.acilis / kur, g.kapanis / kur, g.bar_var, g.bitti, g.yari_spread_bps,
                      g.barlar, g.konum, hashlib.sha256(f"{g.veri_hash}|{kur_kimlik}:{kh}".encode()).hexdigest(), g.bar_ms,
                      g.ciro)


def _ileri_doldur(x: np.ndarray) -> np.ndarray:
    n = x.shape[0]
    ix = np.where(np.isfinite(x), np.arange(n)[:, None], 0)
    np.maximum.accumulate(ix, axis=0, out=ix)
    out = x[ix, np.arange(x.shape[1])]
    out[~np.isfinite(x) & (np.cumsum(np.isfinite(x), axis=0) == 0)] = np.nan  # ilk bardan önce NaN kalsın
    return out


def izgaraya(g: GrupVerisi, j: int, dizi: np.ndarray) -> np.ndarray:
    """Enstrümanın kendi barlarındaki sinyali ızgaraya taşır: bar arasında son değer korunur, ilk bardan önce 0."""
    out = np.full(len(g.t), np.nan)
    out[g.konum[j]] = dizi
    out = _ileri_doldur(out[:, None])[:, 0]
    return np.nan_to_num(out, nan=0.0)


# ------------------------------------------------------------------ point-in-time evren
def gunluk_tablo(g: GrupVerisi) -> dict[str, np.ndarray]:
    """Gün × enstrüman: hacim (kote para; düzeltilmemiş ciro), son kapanış, bar sayısı. Yalnız o günün barlarından."""
    gun = g.t // GUN
    gunler = np.unique(gun)
    gi = np.searchsorted(gunler, gun)
    k = len(g.kimlikler)
    hacim, bar = np.zeros((len(gunler), k)), np.zeros((len(gunler), k))
    kapanis = np.full((len(gunler), k), np.nan)
    for j, b in enumerate(g.barlar):
        gj = gi[g.konum[j]]
        np.add.at(hacim[:, j], gj, g.ciro[j] if g.ciro is not None else b.close * b.volume)
        np.add.at(bar[:, j], gj, 1)
        kapanis[gj, j] = b.close  # aynı güne düşen son bar kazanır (sıralı)
    return {"gun": gunler, "hacim": hacim, "bar": bar, "kapanis": kapanis}


def evren_maskesi(g: GrupVerisi, ilk_n: int | None = None, likidite_gun: int = 30, asgari_gecmis_gun: int = 60,
                  taze_gun: int = 3, asgari_oynaklik: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """(evrende [n, k], likidite [n, k]: son `likidite_gun` günün ortalama günlük hacmi). Bar t için kullanılan gün
    satırı t kapanmadan önce bitmiş son gündür. `asgari_oynaklik`: son 30 günün yıllık oynaklığı bunun altındaysa
    (sabitlenmiş varlık) evrene girmez."""
    d = gunluk_tablo(g)
    ng, k = d["hacim"].shape
    cs = np.vstack([np.zeros((1, k)), np.cumsum(d["hacim"], axis=0)])
    idx = np.arange(ng)
    alt = np.maximum(idx + 1 - likidite_gun, 0)
    lik = (cs[idx + 1] - cs[alt]) / likidite_gun
    var = d["bar"] > 0
    csv = np.vstack([np.zeros((1, k)), np.cumsum(var, axis=0)])
    taze = (csv[idx + 1] - csv[np.maximum(idx + 1 - taze_gun, 0)]) > 0
    gecmis = csv[idx + 1] >= asgari_gecmis_gun
    uygun = taze & gecmis
    if asgari_oynaklik > 0:
        kc = _ileri_doldur(d["kapanis"])
        with np.errstate(invalid="ignore", divide="ignore"):
            lr = np.vstack([np.full((1, k), np.nan), np.diff(np.log(kc), axis=0)])
        from tradebot.cekirdek.gosterge import kayan_std
        sig = np.column_stack([kayan_std(lr[:, j], 30) for j in range(k)]) * math.sqrt(365.25)
        uygun &= np.nan_to_num(sig, nan=0.0) >= asgari_oynaklik
    if ilk_n:
        skor = np.where(uygun, lik, -np.inf)
        sira = np.argsort(np.argsort(-skor, axis=1, kind="stable"), axis=1, kind="stable")
        uygun &= sira < ilk_n
    # bar → gün satırı
    satir = np.searchsorted(d["gun"], (g.t + g.bar_ms) // GUN - 1, side="right") - 1
    gecerli = satir >= 0
    evrende = np.zeros((len(g.t), k), dtype=bool)
    likidite = np.zeros((len(g.t), k))
    evrende[gecerli] = uygun[satir[gecerli]]
    likidite[gecerli] = lik[satir[gecerli]]
    evrende &= ~g.bitti
    return evrende, likidite


# ------------------------------------------------------------------ maliyet
def kripto_ek_kayma_bps(likidite: np.ndarray) -> np.ndarray:
    """Likiditeye bağlı ek kayma (Binance spot, küçük coinler; aleyhte): 30 gün ort. günlük hacim ≥ 100 M$ → 0,
    ≥ 20 M$ → 5 bps, altı → 15 bps."""
    return np.where(likidite >= 1e8, 0.0, np.where(likidite >= 2e7, 5.0, 15.0))


def taraf_matrisi(g: GrupVerisi, modeller: list[MaliyetModeli], ek_bps: np.ndarray | None = None) -> np.ndarray:
    """[n, k] taraf başı maliyet (oran). Spread veriden gelebiliyorsa bar spread'i, yoksa model varsayılanı."""
    n, k = g.acilis.shape
    out = np.empty((n, k))
    for j, mm in enumerate(modeller):
        ys = np.full(n, mm.yari_spread_bps)
        if mm.spread_veriden and g.yari_spread_bps is not None:
            ys = np.where(np.isfinite(g.yari_spread_bps[:, j]), g.yari_spread_bps[:, j], mm.yari_spread_bps)
        out[:, j] = mm.ucret_bps * (1 + mm.ucret_vergisi) + ys + mm.kayma_bps
    if ek_bps is not None:
        out += ek_bps
    return out / 1e4


# ------------------------------------------------------------------ backtest
DURUMLAR = ("normal", "fren_gunluk", "fren_haftalik", "acil_durdurma")


def riski_artirma(h: np.ndarray, kaymis: np.ndarray) -> np.ndarray:
    """Aynı yönde küçülebilir, büyüyemez, ters dönemez (fren ve veto kuralı; canlı risk motoruyla aynı, kural 5)."""
    return np.where(np.sign(h) == np.sign(kaymis), np.sign(h) * np.minimum(np.abs(h), np.abs(kaymis)), 0.0)


def dengele_adim(hedef: np.ndarray, kaymis: np.ndarray, onceki_h: np.ndarray, ilk: bool, islem_ok: np.ndarray,
                 bitti: np.ndarray, durum: str = "normal", veto: np.ndarray | None = None,
                 bant: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bir bar için dengeleme kararı (saf; backtest `calistir_panel` ve canlı paper motoru AYNI fonksiyonu çağırır).

    hedef: bu barda tutulmak istenen ağırlık; kaymis: fiyatla kaymış mevcut ağırlık; onceki_h: önceki barın etkin hedefi.
    Dönüş: (yeni ağırlık, etkin hedef — sonraki barın onceki_h'si, işlem yapılan enstrümanlar)."""
    h = np.nan_to_num(np.asarray(hedef, dtype=float)).copy()
    h[bitti] = 0.0
    if durum == "acil_durdurma":
        h[:] = 0.0
    elif durum != "normal":  # fren: yeni risk yok
        h = riski_artirma(h, kaymis)
    if veto is not None and veto.any():
        h = np.where(veto, riski_artirma(h, kaymis), h)
    degisti = (np.sign(h) != np.sign(onceki_h)) | ilk
    islem = islem_ok & (degisti | (np.abs(h - kaymis) > bant * np.abs(h)))
    return np.where(islem, h, kaymis), h, islem


def calistir_panel(g: GrupVerisi, hedef: np.ndarray, taraf: np.ndarray, modeller: list[MaliyetModeli],
                   bant: float = 0.0, izleyici=None, fiyat: np.ndarray | None = None,
                   veto: np.ndarray | None = None) -> Sonuc:
    """hedef [n, k]: bar t kapanışında verilen ağırlık (özkaynağa oran). Dönüş: kol düzeyinde Sonuc (pozisyon = brüt
    maruziyet, devir = Σ|Δw|). `fiyat`: yürütme fiyatı (varsayılan açılış).

    Dengeleme: yön değişince (giriş, çıkış, ters dönüş) her zaman işlem; aynı yönde ağırlık hedeften `bant` × |hedef|'ten
    fazla saparsa hedefe döner (oransal bant; oynaklık ölçeğinin her bar küçük işlem üretmesini önler). bant = 0: her bar
    hedefe dengele (`backtest.calistir(bant=0)` ile birebir).

    `veto` [n, k]: zekâ katmanı vetosu (bar i'nin açılışında geçerli olanlar; `veto_maskesi`). Vetolu enstrümanda risk
    artırılamaz: aynı yönde küçülebilir, büyüyemez, ters dönemez (canlı risk motoruyla aynı kural, kural 5)."""
    p = g.acilis if fiyat is None else fiyat
    n, k = p.shape
    if n < 3 or hedef.shape != (n, k):
        raise ValueError("hedef [n, k] ve n ≥ 3 olmalı")
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.nan_to_num(p[1:] / p[:-1] - 1.0)
    h_all = np.vstack([np.zeros((1, k)), np.nan_to_num(hedef[:-1])])  # bar i'de tutulacak = hedef[i-1]
    sure = np.diff(g.t).astype(float)
    fin_uzun = np.array([m.finansman_yillik for m in modeller])
    fin_kisa = np.array([m.finansman_yillik + m.aciga_satis_yillik for m in modeller])
    w_all, devir, brut, mal, net = np.empty((n - 1, k)), np.empty(n - 1), np.empty(n - 1), np.empty(n - 1), np.empty(n - 1)
    kaymis, onceki_h, oz = np.zeros(k), np.zeros(k), 1.0
    durumlar = np.zeros(n - 1, dtype=np.int8)
    for i in range(n - 1):
        durum = "normal"
        if izleyici is not None:
            durum = izleyici.guncelle(oz, int(g.t[i])).value
            durumlar[i] = DURUMLAR.index(durum)
        w, onceki_h, _ = dengele_adim(h_all[i], kaymis, onceki_h, i == 0, g.bar_var[i] | g.bitti[i], g.bitti[i], durum,
                                      veto[i] if veto is not None else None, bant)
        dv = np.abs(w - kaymis)
        carpan = np.where(g.bitti[i], KALKAN_MALIYET_CARPANI, 1.0)
        fin = np.where(w >= 0, fin_uzun, fin_kisa) * np.abs(w) * sure[i] / YIL_MS
        c = float((dv * taraf[i] * carpan).sum() + fin.sum())
        b_ = float((w * r[i]).sum())
        nt = b_ - c
        w_all[i], devir[i], brut[i], mal[i], net[i] = w, dv.sum(), b_, c, nt
        kaymis = w * (1.0 + r[i]) / (1.0 + nt) if abs(1.0 + nt) > 1e-12 else np.zeros(k)
        oz *= 1.0 + nt
    return Sonuc(t=g.t[:-1], pozisyon=np.abs(w_all).sum(axis=1), brut=brut, maliyet=mal, net=net, devir=devir,
                 ozkaynak=np.cumprod(1.0 + net), durum=durumlar if izleyici is not None else None)


def veto_maskesi(g: GrupVerisi, olaylar: list[tuple[str, int, int | None]]) -> np.ndarray:
    """[n, k] veto maskesi. `olaylar`: (enstrüman, gecerli_ms, bitis_ms|None). Bar i'nin kararı i'nin açılışında
    uygulanır; veto yalnız `gecerli_ms ≤ t[i]` ise görünür (point-in-time), `bitis_ms`'te kalkar."""
    m = np.zeros((len(g.t), len(g.kimlikler)), dtype=bool)
    sutun = {k: j for j, k in enumerate(g.kimlikler)}
    for kimlik, bas, bit in olaylar:
        j = sutun.get(kimlik)
        if j is None:
            continue
        m[:, j] |= (g.t >= bas) & ((g.t < bit) if bit is not None else True)
    return m
