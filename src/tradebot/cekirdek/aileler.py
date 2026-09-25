"""Turnuva aileleri, dalga 1 (Final Doküman §Strateji turnuvası). Hepsi saf ve nedenseldir.

Tek enstrüman fonksiyonları `Barlar` alır, bar başına yön/sinyal döndürür (∈ [-1, 1]; yön kısıtı StratejiTanimi.yon).
Boyut (oynaklık hedefi, kol içi ağırlık) çekirdeğin dışında, `boyut.panel_oynaklik_hedefi`'nde.
Kesitsel fonksiyonlar `Panel` alır, [n, k] ağırlık döndürür.

Aile → fonksiyonlar:
- trend: tsmom (ornek.py), ma_yon, donchian_ls
- ortalamaya_donus: zskor_donus, rsi_donus
- takvim: ay_donumu
- kesitsel_momentum: kesitsel_momentum (Panel)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from tradebot.cekirdek.gosterge import kayan_max, kayan_min, kayan_std, sma
from tradebot.cekirdek.temel import Barlar

GUN_MS = 86_400_000
HAFTA_MS = 7 * GUN_MS
PAZARTESI_KAYMA_MS = 4 * GUN_MS


# ---------------------------------------------------------------- trend
def ma_yon(b: Barlar, hizli: int = 20, yavas: int = 100) -> np.ndarray:
    """Hızlı ortalama yavaşın üstünde +1, altında −1 (yavaş tanımlanana kadar 0). Yalnız long kolda 1/0."""
    h, y = sma(b.close, hizli), sma(b.close, yavas)
    return np.where(np.isnan(y), 0.0, np.sign(h - y))


def donchian_ls(b: Barlar, giris: int = 20, cikis: int = 10) -> np.ndarray:
    """Kapanış önceki `giris` barın tepesini aşınca +1, dibini kırınca −1; long `cikis` barın dibinde, short `cikis`
    barın tepesinde kapanır (durumlu, nedensel). Yalnız long kolda short sinyalleri 0'a kırpılır."""
    ust, alt = kayan_max(b.high, giris), kayan_min(b.low, giris)
    c_alt, c_ust = kayan_min(b.low, cikis), kayan_max(b.high, cikis)
    out = np.zeros(len(b))
    poz = 0.0
    for i in range(len(b)):
        c = b.close[i]
        if poz > 0 and not np.isnan(c_alt[i]) and c < c_alt[i]:
            poz = 0.0
        elif poz < 0 and not np.isnan(c_ust[i]) and c > c_ust[i]:
            poz = 0.0
        if poz == 0.0 and not np.isnan(ust[i]):
            if c > ust[i]:
                poz = 1.0
            elif c < alt[i]:
                poz = -1.0
        out[i] = poz
    return out


# ---------------------------------------------------------------- ortalamaya dönüş
def zskor_donus(b: Barlar, pencere: int = 20, giris: float = 2.0, cikis: float = 0.5) -> np.ndarray:
    """z = (kapanış − SMA) / std. z < −giris → +1, z > giris → −1; |z| < cikis'e dönünce kapat."""
    m = sma(b.close, pencere)
    s = kayan_std(b.close, pencere)
    out = np.zeros(len(b))
    poz = 0.0
    for i in range(len(b)):
        if np.isnan(m[i]) or np.isnan(s[i]) or s[i] <= 0:
            out[i] = poz
            continue
        z = (b.close[i] - m[i]) / s[i]
        if poz > 0 and z > -cikis or poz < 0 and z < cikis:
            poz = 0.0
        if poz == 0.0:
            poz = 1.0 if z < -giris else (-1.0 if z > giris else 0.0)
        out[i] = poz
    return out


def rsi(close: np.ndarray, n: int) -> np.ndarray:
    """Wilder RSI (nedensel, özyinelemeli ortalama)."""
    out = np.full(len(close), np.nan)
    if len(close) <= n:
        return out
    d = np.diff(close)
    kaz, kay = np.maximum(d, 0.0), np.maximum(-d, 0.0)
    ok, oy = kaz[:n].mean(), kay[:n].mean()
    for i in range(n, len(close)):
        if i > n:
            ok = (ok * (n - 1) + kaz[i - 1]) / n
            oy = (oy * (n - 1) + kay[i - 1]) / n
        out[i] = 100.0 if oy == 0 else 100.0 - 100.0 / (1.0 + ok / oy)
    return out


def rsi_donus(b: Barlar, n: int = 2, alt: float = 10.0, trend: int = 200, cikis_ma: int = 5) -> np.ndarray:
    """Trend yönünde kısa vadeli aşırılık: kapanış > SMA(trend) ve RSI(n) < alt → +1; kapanış SMA(cikis_ma)'yı
    aşınca çık. Simetrik short: kapanış < SMA(trend) ve RSI > 100 − alt → −1; SMA(cikis_ma) altına inince çık."""
    r = rsi(b.close, n)
    tr, cm = sma(b.close, trend), sma(b.close, cikis_ma)
    out = np.zeros(len(b))
    poz = 0.0
    for i in range(len(b)):
        c = b.close[i]
        if poz > 0 and c > cm[i] or poz < 0 and c < cm[i]:
            poz = 0.0
        if poz == 0.0 and not (np.isnan(tr[i]) or np.isnan(r[i])):
            if c > tr[i] and r[i] < alt:
                poz = 1.0
            elif c < tr[i] and r[i] > 100.0 - alt:
                poz = -1.0
        out[i] = poz
    return out


# ---------------------------------------------------------------- takvim
def _gun_bilgisi(t_ms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(ayın günü 1..31, ayın gün sayısı). Takvim günleri zaman damgasından; fiyat verisine bakmaz."""
    g = np.asarray(t_ms, dtype=np.int64).astype("datetime64[ms]").astype("datetime64[D]")
    ay = g.astype("datetime64[M]")
    gun = (g - ay).astype(np.int64) + 1
    uzunluk = ((ay + np.timedelta64(1, "M")).astype("datetime64[D]") - ay.astype("datetime64[D]")).astype(np.int64)
    return gun, uzunluk


def ay_donumu(b: Barlar, son: int = 4, ilk: int = 3) -> np.ndarray:
    """Ay dönümü etkisi: ayın son `son` takvim günü ile ilk `ilk` takvim günü boyunca tut. (Dalga dosyasında
    `son_gun`/`ilk_gun` olarak yazılır; yalnız 1d'de koşar, gün → bar çevrimi birebirdir.)

    Karar bar t kapanışında: bar t'nin günü pencerenin hemen öncesindeyse ya da içindeyse (bir sonraki bar pencerede
    kalacak şekilde) +1. Takvim günü yaklaşımı (seans takvimi çekirdeğe girmez)."""
    gun, uzunluk = _gun_bilgisi(b.t)
    kalan = uzunluk - gun  # ay sonuna kalan takvim günü
    giris = kalan <= son                # ertesi bar ay sonu penceresine düşer
    icinde = gun < ilk                  # ertesi bar hâlâ ayın ilk günlerinde
    return (giris | icinde).astype(float)


# ---------------------------------------------------------------- kesitsel (panel)
@dataclass(frozen=True)
class Panel:
    """Bir piyasa grubunun ortak zaman ızgarasındaki barları. [n, k] diziler; `close` ileri doldurulmuştur (hiç bar
    yoksa NaN). `evrende[t, j]`: j, t anında (yalnız t'ye kadarki veriyle) kolun evreninde mi (point-in-time)."""

    t: np.ndarray
    close: np.ndarray
    evrende: np.ndarray

    def __len__(self) -> int:
        return len(self.t)

    def kes(self, n: int) -> Panel:
        return Panel(self.t[:n], self.close[:n], self.evrende[:n])


def hafta_basi(t_ms: np.ndarray) -> np.ndarray:
    """Bar t, UTC haftasının (Pazartesi 00:00) son barı mı: ertesi barın haftası farklı olacak mı sorusu geleceği
    gerektirir; bunun yerine haftanın İLK barı işaretlenir (karar o barın kapanışında)."""
    h = (np.asarray(t_ms, dtype=np.int64) - PAZARTESI_KAYMA_MS) // HAFTA_MS
    return np.r_[True, h[1:] != h[:-1]]


def kesitsel_momentum(p: Panel, geriye: int = 30, atla: int = 0, ust_n: int = 3, mutlak: bool = True,
                      haftalik: bool = True) -> np.ndarray:
    """Evrendeki enstrümanları [t − geriye, t − atla] getirisine göre sırala, ilk `ust_n`'ye eşit ağırlık (toplam 1).
    `mutlak`: yalnız kendi getirisi pozitif olanlar tutulur (kalan ağırlık nakitte). `haftalik`: sıralama yalnız
    haftanın ilk barında yenilenir, arada ağırlık sabit (devir düşük)."""
    n, k = p.close.shape
    out = np.zeros((n, k))
    yenile = hafta_basi(p.t) if haftalik else np.ones(n, dtype=bool)
    son = np.zeros(k)
    for i in range(n):
        if i >= geriye and yenile[i]:
            bas, bit = p.close[i - geriye], p.close[i - atla]
            with np.errstate(invalid="ignore", divide="ignore"):
                g = bit / bas - 1.0
            gecerli = p.evrende[i] & np.isfinite(g)
            son = np.zeros(k)
            if gecerli.any():
                aday = np.flatnonzero(gecerli)
                sirali = aday[np.argsort(-g[aday], kind="stable")][:ust_n]
                if mutlak:
                    sirali = sirali[g[sirali] > 0]
                son[sirali] = 1.0 / ust_n
        out[i] = np.where(p.evrende[i], son, 0.0)
    return out


def panel_nedensellik_testi(fonk, p: Panel, deneme: int = 10, tohum: int = 0, **param) -> None:
    """Panel fonksiyonu için gelecek-bozma testi: t sonrası fiyatlar bozulunca out[: t + 1] değişmemeli."""
    rng = np.random.default_rng(tohum)
    temel = fonk(p, **param)
    n = len(p)
    for _ in range(deneme):
        t = int(rng.integers(n // 4, n - 2))
        c = p.close.copy()
        c[t + 1:] *= rng.uniform(0.5, 2.0, c[t + 1:].shape)
        yeni = fonk(Panel(p.t, c, p.evrende), **param)
        if not np.array_equal(yeni[: t + 1], temel[: t + 1]):
            raise AssertionError(f"{getattr(fonk, '__name__', fonk)} geleceği görüyor (t={t})")


# ---------------------------------------------------------------- gün içi kırılım
def abd_yaz_saati(gun: np.ndarray) -> np.ndarray:
    """ABD yaz saati (2007 sonrası kural): Mart'ın 2. Pazarı ≤ gün < Kasım'ın 1. Pazarı. `gun`: datetime64[D]."""
    g = np.asarray(gun, dtype="datetime64[D]")
    yil = g.astype("datetime64[Y]")
    mart = (yil + np.timedelta64(2, "M")).astype("datetime64[D]")
    kasim = (yil + np.timedelta64(10, "M")).astype("datetime64[D]")

    def pazar(d):  # d'den itibaren ilk Pazar (1970-01-01 Perşembe → Pazartesi=0 için +3)
        hg = (d.astype(np.int64) + 3) % 7
        return d + ((6 - hg) % 7).astype("timedelta64[D]")

    return (g >= pazar(mart) + np.timedelta64(7, "D")) & (g < pazar(kasim))


def ny_seans(t_ms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bar açılışının UTC gününde NYSE normal seansının (09:30–16:00 NY) UTC açılış ve kapanışı (ms). Tatil/yarım gün
    burada bilinmez; çekirdek dışında borsa takvimi maskesiyle (evrende) uygulanır."""
    t = np.asarray(t_ms, dtype=np.int64)
    gun0 = t // GUN_MS * GUN_MS
    yaz = abd_yaz_saati(gun0.astype("datetime64[ms]").astype("datetime64[D]"))
    acilis = gun0 + np.where(yaz, 13 * 3_600_000 + 30 * 60_000, 14 * 3_600_000 + 30 * 60_000)
    return acilis, acilis + 390 * 60_000


def acilis_araligi_kirilim(b: Barlar, aralik_dk: int = 30, cikis_dk: int = 15) -> np.ndarray:
    """NY seansının ilk `aralik_dk` dakikasının tepesi/dibi (açılış aralığı). Aralık kapandıktan sonra kapanış tepeyi
    aşarsa +1, dibi kırarsa −1 (günde en fazla bir giriş). Stop: karşı uç (kapanışla). Kapanıştan `cikis_dk` önce 0.
    Bar süresi zaman damgalarından (en küçük aralık). Karar bar kapanışında; dolum sonraki barda (motor)."""
    n = len(b)
    out = np.zeros(n)
    if n < 2:
        return out
    bar_ms = int(np.min(np.diff(b.t)))
    acilis, kapanis = ny_seans(b.t)
    bitis = np.asarray(b.t, dtype=np.int64) + bar_ms  # bar kapanış anı
    gun = np.asarray(b.t, dtype=np.int64) // GUN_MS
    aralik_ms, cikis_ms = aralik_dk * 60_000, cikis_dk * 60_000
    poz, son_gun, ust, alt, girdi = 0.0, -1, -np.inf, np.inf, False
    for i in range(n):
        if gun[i] != son_gun:
            son_gun, poz, ust, alt, girdi = gun[i], 0.0, -np.inf, np.inf, False
        t, a = int(b.t[i]), int(acilis[i])
        if a <= t < a + aralik_ms:  # aralık barı
            ust, alt = max(ust, b.high[i]), min(alt, b.low[i])
        tamam = bitis[i] >= a + aralik_ms and np.isfinite(ust)
        acik = bitis[i] < kapanis[i] - cikis_ms and t >= a
        if not acik:
            poz = 0.0
        elif tamam:
            c = b.close[i]
            if poz > 0 and c < alt or poz < 0 and c > ust:
                poz = 0.0  # stop: karşı uç
            elif poz == 0.0 and not girdi:
                if c > ust:
                    poz, girdi = 1.0, True
                elif c < alt:
                    poz, girdi = -1.0, True
        out[i] = poz
    return out
