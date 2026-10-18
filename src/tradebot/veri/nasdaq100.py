"""Nasdaq-100 point-in-time üyelik (kural 9: evren point-in-time, ham veri değişmez, hash'i kimliğidir).

Kaynak: `jmccarrell/n100tickers` (MIT), yıl başına bir YAML: `tickers_on_Jan_1` + `changes` (tarih → `union` eklenen,
`difference` çıkan). Değişiklikler Nasdaq duyurularındaki yürürlük tarihindedir ve semboller o gün işlem gördüğü
haliyle yazılır (2010'da PCLN, bugün BKNG). Kapsam 2007-02-01 → bugün. Ham dosyalar SABİT bir commit'ten indirilir
(`config/nasdaq.yaml` → `uyelik.commit`): kaynak sonradan düzeltilse de koşu aynı girdiyle yeniden üretilir; commit
değiştirmek yeni bir veri sürümüdür.

Tuzaklar (2026-10-18 ölçümü):
- YAML 1.1'de `ON` (ON Semiconductor) bool'a dönüşür: dosyalar `BaseLoader` ile (her değer metin) okunur.
- Yahoo yalnız bugün işlem gören sembolleri tutar: 285 tarihî üyenin 81'i yok (satın alınan, kapanan; ATVI, CELG, XLNX,
  YHOO…). Bazı semboller başka şirkete geçmiş (FB, PCLN, GENZ, LIFE artık başka varlık). Bu yüzden:
  1. `sembol_esleme`: aynı şirketin yeni sembolü (FB → META). Elle, gerekçeli.
  2. Dönem bazlı kapsam: bir üyelik dönemi yalnız fiyat serisi o dönemi gerçekten kapsıyorsa evrene girer
     (`kapsam_maskesi`); başka varlığa geçmiş sembolün sonraki verisi eski üyelik dönemine sızmaz.
  3. `dislanan`: Yahoo'da aynı sembolle BAŞKA bir şirketin geçmişi olan semboller (GOLD = Gold.com, Randgold değil).
  Kalan hayatta kalma yanlılığı (verisi olmayan üyeler) ölçülür ve raporlanır (`kapsam_raporu`), gizlenmez.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import yaml

from tradebot.veri.depo import HamDepo
from tradebot.veri.http import NazikIstemci

AYAR_YOLU = Path(__file__).resolve().parents[3] / "config" / "nasdaq.yaml"
URL = "https://raw.githubusercontent.com/jmccarrell/n100tickers/{commit}/src/nasdaq_100_ticker_history/" \
      "n100-ticker-changes-{yil}.yaml"
KAYNAK = "n100tickers"
GUN_MS = 86_400_000


def ayar_oku(yol: Path = AYAR_YOLU) -> dict:
    return yaml.safe_load(Path(yol).read_text(encoding="utf-8"))


def _gun_ms(g: str | date) -> int:
    d = date.fromisoformat(g) if isinstance(g, str) else g
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)


@dataclass(frozen=True)
class Donem:
    sembol: str            # o gün işlem gören n100 sembolü
    bas_ms: int            # üyeliğin ilk günü (yürürlük günü, UTC 00:00)
    bit_ms: int | None     # üyeliğin bittiği gün (o gün artık üye değil); None: hâlâ üye


def yil_coz(icerik: bytes) -> tuple[int, list[str], list[tuple[str, list[str], list[str]]]]:
    """(yıl, 1 Ocak üyeleri, [(tarih, eklenen, çıkan)] tarih sıralı)."""
    d = yaml.load(icerik.decode("utf-8"), Loader=yaml.BaseLoader)   # BaseLoader: `ON` metin kalır
    degisim = [(t, list(c.get("union", []) or []), list(c.get("difference", []) or []))
               for t, c in sorted((d.get("changes") or {}).items())]
    return int(d["year"]), list(d["tickers_on_Jan_1"]), degisim


def donemler(yillar: dict[int, bytes]) -> list[Donem]:
    """Yıllık dosyalardan üyelik dönemleri. İlk yılın 1 Ocak listesi başlangıç durumudur; sonraki yılların 1 Ocak
    listesi değişikliklerle elde edilen durumla tutarlı olmalı (değilse hata: kaynak bozuk ya da eksik)."""
    if not yillar:
        raise ValueError("üyelik dosyası yok")
    uye: dict[str, int] = {}
    out: list[Donem] = []
    for i, yil in enumerate(sorted(yillar)):
        y, ocak, degisim = yil_coz(yillar[yil])
        if y != yil:
            raise ValueError(f"dosya yılı {y} ≠ {yil}")
        if i == 0:
            uye = {s: _gun_ms(f"{yil}-01-01") for s in ocak}
        elif set(ocak) != set(uye):
            fark = sorted(set(ocak) ^ set(uye))
            raise ValueError(f"{yil}-01-01 üyeleri değişikliklerle tutarsız: {fark[:10]}")
        for t, ekle, cik in degisim:
            an = _gun_ms(t)
            for s in cik:
                if s not in uye:
                    raise ValueError(f"{t}: üye olmayan {s} çıkarılıyor")
                out.append(Donem(s, uye.pop(s), an))
            for s in ekle:
                if s in uye:
                    raise ValueError(f"{t}: {s} zaten üye")
                uye[s] = an
    out += [Donem(s, b, None) for s, b in uye.items()]
    return sorted(out, key=lambda d: (d.sembol, d.bas_ms))


def indir(ham: HamDepo, ayar: dict, http: NazikIstemci | None = None, bit_yil: int | None = None) -> dict[int, bytes]:
    """Sabit commit'in yıllık dosyaları (ham depoya; aynı içerik yeniden yazılmaz)."""
    http = http or NazikIstemci("n100tickers", aralik_sn=0.3)
    u = ayar["uyelik"]
    out = {}
    for yil in range(int(u["ilk_yil"]), (bit_yil or datetime.now(UTC).year) + 1):
        icerik = http.al(URL.format(commit=u["commit"], yil=yil))
        ham.kaydet(KAYNAK, f"{u['commit'][:12]}/{yil}", icerik, "yaml")
        out[yil] = icerik
    return out


def yerel(ham: HamDepo, ayar: dict) -> dict[int, bytes]:
    """Ham depodaki sabit commit dosyaları (ağsız; backtest ve canlı düğüm bunu okur)."""
    on_ek = f"{ayar['uyelik']['commit'][:12]}/"
    return {int(a.removeprefix(on_ek)): y.read_bytes() for a, y, _ in ham.dosyalar(KAYNAK, on_ek)}


def kimlik_donemleri(ds: list[Donem], ayar: dict, piyasa: str = "NASDAQ") -> dict[str, list[tuple[int, int | None]]]:
    """Enstrüman kimliği → üyelik dönemleri. Eşlenen semboller yeni sembolün kimliğine birleşir (FB + META → META);
    dışlananlar düşer. Aynı kimliğin bitişik dönemleri (sembol değişikliği günü) birleştirilir."""
    esle = ayar.get("sembol_esleme") or {}
    disla = set((ayar.get("dislanan") or {}).keys())
    out: dict[str, list[tuple[int, int | None]]] = {}
    for d in ds:
        if d.sembol in disla:
            continue
        out.setdefault(f"{piyasa}:{esle.get(d.sembol, d.sembol)}", []).append((d.bas_ms, d.bit_ms))
    for k, v in out.items():
        v.sort(key=lambda x: x[0])
        birlesik: list[tuple[int, int | None]] = []
        for b, e in v:
            if birlesik and birlesik[-1][1] is not None and birlesik[-1][1] >= b:
                birlesik[-1] = (birlesik[-1][0], e if e is None or birlesik[-1][1] is None else max(e, birlesik[-1][1]))
            else:
                birlesik.append((b, e))
        out[k] = birlesik
    return out


def uyelik_maskesi(t: np.ndarray, kimlikler: list[str], donem: dict[str, list[tuple[int, int | None]]]) -> np.ndarray:
    """[n, k]: bar t (seans günü, UTC 00:00 etiketli) günü kimlik üye mi. Karar t kapanışında verilir; ekleme ve
    çıkarmalar yürürlükten günler önce duyurulduğu için t gününün üyeliğini kullanmak geleceği görmek değildir."""
    t = np.asarray(t, dtype=np.int64)
    m = np.zeros((len(t), len(kimlikler)), dtype=bool)
    for j, k in enumerate(kimlikler):
        for b, e in donem.get(k, []):
            m[:, j] |= (t >= b) & ((t < e) if e is not None else True)
    return m


def kapsam_maskesi(uyelik: np.ndarray, bar_var: np.ndarray, tolerans_gun: int = 10) -> np.ndarray:
    """Üyelik dönemi yalnız fiyat serisi dönemin başından (en çok `tolerans_gun` seans gecikmeyle) varsa kullanılır.
    Serisi dönemin ortasında başlayan sembol (yeniden kullanılan sembol, kaynakta kesilmiş geçmiş) o dönem için
    evrene girmez: başka bir şirketin fiyatı üyelik dönemine sızmasın. [n, k] → [n, k]."""
    n, k = uyelik.shape
    out = np.zeros_like(uyelik)
    for j in range(k):
        u = uyelik[:, j]
        if not u.any():
            continue
        bas = np.flatnonzero(u & ~np.r_[False, u[:-1]])          # dönem başları
        bit = np.flatnonzero(u & ~np.r_[u[1:], False]) + 1       # dönem sonları (hariç)
        ilk_bar = np.flatnonzero(bar_var[:, j])
        if len(ilk_bar) == 0:
            continue
        for b, e in zip(bas, bit, strict=True):
            ici = ilk_bar[(ilk_bar >= b) & (ilk_bar < e)]
            if len(ici) and ici[0] - b <= tolerans_gun:
                out[b:e, j] = True
    return out


def kapsam_raporu(t: np.ndarray, uyelik: np.ndarray, kapsam: np.ndarray) -> dict:
    """Yıl başına üye-gün kapsamı: verisi olan üye günlerinin oranı (hayatta kalma yanlılığının büyüklüğü)."""
    yil = np.asarray(t, dtype="datetime64[ms]").astype("datetime64[Y]").astype(int) + 1970
    out = {}
    for y in np.unique(yil):
        s = yil == y
        u = int(uyelik[s].sum())
        out[int(y)] = {"uye_gun": u, "kapsanan": round(float(kapsam[s].sum() / u), 4) if u else None,
                       "ort_uye": round(float(uyelik[s].sum(axis=1).mean()), 1),
                       "ort_kapsanan": round(float(kapsam[s].sum(axis=1).mean()), 1)}
    return out
