"""Turnuva aileleri, dalga 1 (Final Doküman §Strateji turnuvası). Hepsi saf ve nedenseldir.

Tek enstrüman fonksiyonları `Barlar` alır, bar başına yön/sinyal döndürür (∈ [-1, 1]; yön kısıtı StratejiTanimi.yon).
Boyut (oynaklık hedefi, kol içi ağırlık) çekirdeğin dışında, `boyut.panel_oynaklik_hedefi`'nde.
Kesitsel fonksiyonlar `Panel` alır, [n, k] ağırlık döndürür.

Aile → fonksiyonlar:
- trend: tsmom (ornek.py), ma_yon, donchian_ls
- ortalamaya_donus: zskor_donus, rsi_donus
- takvim: ay_donumu
- kesitsel_momentum: kesitsel_momentum (Panel)
- tasima: tasima (VİOP 2, TL taşıma; docs/turnuva/VIOP-2.md)
- doviz_kesitsel: doviz_kesitsel (Panel; dalga 9, G10 taşıma/momentum)
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


# ---------------------------------------------------------------- taşıma
def tasima(b: Barlar, ufuk: int = 0, pencere: int = 0, uzun: int = 250, kat: float = 1.5) -> np.ndarray:
    """TL taşıma (VİOP 2): USDTRY vadeli sürekli serisinde KISA (−1). Seri faiz farkını içerir (baz erimesi): kısa
    pozisyon TL–USD faiz primini toplar, TL'nin değer kaybını öder.

    Filtreler (her biri kapatır, 0; ısınmada da 0 — bilinmeyen durumda pozisyon yok):
    - `ufuk` > 0: serinin son `ufuk` bar getirisi > 0 → TL taşımadan hızlı değer kaybediyor (prim yetmiyor).
    - `pencere` > 0: son `pencere` barın getiri oynaklığı, son `uzun` bardaki oynaklıkların medyanının `kat` katını
      aşarsa → kriz (2018, 2021 tipi sıçrama). Boyutsuz: yıllıklaştırma gerekmez.
    """
    n = len(b)
    out = np.full(n, -1.0)
    c = b.close
    if ufuk > 0:
        gecmis = np.full(n, np.nan)
        gecmis[ufuk:] = c[ufuk:] / c[:-ufuk] - 1.0
        out[~(gecmis <= 0)] = 0.0                      # NaN (ısınma) ya da pozitif → kapalı
    if pencere > 0:
        r = np.r_[np.nan, np.diff(np.log(c))]
        sd = kayan_std(r, pencere)
        med = np.full(n, np.nan)
        for t in range(uzun - 1, n):                   # nedensel: [t − uzun + 1, t]
            w = sd[t - uzun + 1: t + 1]
            if np.isfinite(w).sum() >= uzun // 2:
                med[t] = np.nanmedian(w)
        out[~(sd <= kat * med)] = 0.0                  # NaN ya da kriz → kapalı
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
    # Döviz grubu (dalga 9): `tasima[t, j]` = j'yi UZUN tutmanın t'de bilinen yıllık faiz farkı (r_taban − r_kote);
    # `para_yon[j]` = +1 (XXXUSD: uzun = yabancı para uzun) ya da −1 (USDXXX). Diğer gruplarda None.
    tasima: np.ndarray | None = None
    para_yon: np.ndarray | None = None
    # Döviz akış grubu (dalga 10): `paralar[j]` = j'nin USD dışındaki parası (ör. "EUR", "JPY").
    paralar: tuple[str, ...] | None = None

    def __len__(self) -> int:
        return len(self.t)

    def kes(self, n: int) -> Panel:
        return Panel(self.t[:n], self.close[:n], self.evrende[:n],
                     None if self.tasima is None else self.tasima[:n], self.para_yon, self.paralar)


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


DOVIZ_OLCUTLER = ("tasima", "momentum", "birlesik", "dolar")


def _sira(x: np.ndarray) -> np.ndarray:
    """Küçükten büyüğe sıra (0..m−1), eşitlikte kararlı."""
    r = np.empty(len(x))
    r[np.argsort(x, kind="stable")] = np.arange(len(x))
    return r


def doviz_kesitsel(p: Panel, olcut: str = "tasima", n: int = 2, geriye: int = 63, haftalik: bool = True) -> np.ndarray:
    """G10 döviz kesitseli (dalga 9; docs/turnuva/Dalga-9-Doviz.md). Her enstrüman bir yabancı paradır (karşısı USD);
    USD'nin kendisi puanı 0 olan yedinci para olarak sıralamaya girer.

    Para puanı (USD'ye karşı, t'de bilinenle):
    - `tasima`: r_para − r_USD (Lustig-Verdelhan / Menkhoff 2012 taşıma portföyü).
    - `momentum`: paranın USD'ye karşı son `geriye` bar log getirisi (seri nakit üstü: taşıma dahil).
    - `birlesik`: iki sıranın ortalaması.
    En yüksek `n` para uzun, en düşük `n` kısa, her biri 1/n (para uzayında dolar-nötr). USD uçlardaysa ağırlığı
    örtüktür (diğer bacakların toplamı). `dolar` (Lustig-Roussanov-Verdelhan 2014): yabancı faizlerin ortalaması USD'nin
    üstündeyse bütün yabancı paralar uzun, değilse kısa, her biri 1/m.
    Enstrüman ağırlığı = para_yon × para ağırlığı. `haftalik`: yalnız haftanın ilk barında yenilenir."""
    if olcut not in DOVIZ_OLCUTLER:
        raise ValueError(f"bilinmeyen ölçüt: {olcut}")
    if p.para_yon is None or (olcut != "momentum" and p.tasima is None):
        raise ValueError("doviz_kesitsel: panelde para_yon/tasima yok (grup tanımında doviz: true)")
    nb, k = p.close.shape
    yon = np.asarray(p.para_yon, dtype=float)
    out = np.zeros((nb, k))
    yenile = hafta_basi(p.t) if haftalik else np.ones(nb, dtype=bool)
    son = np.zeros(k)
    with np.errstate(invalid="ignore", divide="ignore"):
        lc = np.log(p.close)
    for i in range(nb):
        if yenile[i]:
            son = np.zeros(k)
            tas = yon * p.tasima[i] if p.tasima is not None else np.full(k, np.nan)
            mom = yon * (lc[i] - lc[i - geriye]) if i >= geriye else np.full(k, np.nan)
            if olcut in ("tasima", "dolar"):
                puan, gerek = tas, np.isfinite(tas)
            elif olcut == "momentum":
                puan, gerek = mom, np.isfinite(mom)
            else:
                puan, gerek = None, np.isfinite(tas) & np.isfinite(mom)
            gecerli = p.evrende[i] & gerek
            aday = np.flatnonzero(gecerli)
            if olcut == "dolar":
                if len(aday) > 0:
                    isaret = 1.0 if tas[aday].mean() > 0 else -1.0
                    son[aday] = isaret / len(aday)
            elif len(aday) + 1 >= 2 * n:
                if olcut == "birlesik":
                    x = (_sira(np.r_[tas[aday], 0.0]) + _sira(np.r_[mom[aday], 0.0])) / 2.0
                else:
                    x = np.r_[puan[aday], 0.0]
                s = np.argsort(x, kind="stable")      # son eleman (indeks len(aday)) USD
                para = np.zeros(len(aday) + 1)
                para[s[-n:]] += 1.0 / n
                para[s[:n]] -= 1.0 / n
                son[aday] = para[:-1]
            son = son * yon
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
        ts = None
        if p.tasima is not None:
            ts = p.tasima.copy()
            ts[t + 1:] += rng.normal(0.0, 0.05, ts[t + 1:].shape)
        yeni = fonk(Panel(p.t, c, p.evrende, ts, p.para_yon, p.paralar), **param)
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
