"""Yüksek etkili ABD veri takvimi: FOMC kararı, tarım dışı istihdam (NFP), TÜFE (CPI); dalga 14'ten beri ayrıca ÜFE
(PPI) ve haftalık işsizlik başvuruları (ISSIZLIK). Haber filtresi (`yukle`) yalnız ilk üçünü okur (Altın M15 ön kaydı).

Kaynaklar resmidir ve tarihler yayından önce ilan edilir (BLS yıllık takvim, Fed toplantı takvimi), yani filtre geleceği
görmez. Olağanüstü FOMC toplantıları ve ertelenen/iptal edilen BLS yayınları arşivde gerçekleştiği gibi durur.
- FOMC: federalreserve.gov/monetarypolicy/fomccalendars.htm → `pressreleases/monetaryYYYYMMDDa.htm` (karar metni),
  14:00 New York (2013'ten beri sabit saat).
- NFP / CPI / PPI: bls.gov/bls/news-release/{empsit,cpi,ppi}.htm arşivi → `archives/<ad>_MMDDYYYY.htm`, 08:30 New
  York. BLS, tarayıcı taklidi yapan istemciye 403 veriyor; iletişim adresli dürüst User-Agent ile açılıyor (ölçüldü).
- ISSIZLIK: Çalışma Bakanlığı (DOL) haftalık başvuruları kuralla yayımlar: her perşembe 08:30 New York; perşembe
  federal tatilse (yılbaşı, Juneteenth 2021'den, 4 Temmuz, Gaziler Günü, Şükran Günü, Noel) bir gün önce, çarşamba.
  Kural önceden bilinir; arşiv yok, tarih üretilir (`issizlik_tarihleri`). Federal hükümet kapanmasında DOL ulusal
  raporu yayımlamadı (1 Ekim → 12 Kasım 2025; kapanma o an kamuya açıktı, geleceği görmek değil): bu perşembeler yok.
Çıktı: `config/haber_takvimi.yaml` (commit edilir; kaynak sayfaların hash'i ham depoda).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from tradebot.veri.depo import HamDepo
from tradebot.veri.http import NazikIstemci

NY = ZoneInfo("America/New_York")
FOMC = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS = "https://www.bls.gov/bls/news-release/{}.htm"
CIKTI = Path(__file__).resolve().parents[3] / "config" / "haber_takvimi.yaml"


def ny_ms(tarih: str, saat: int, dakika: int) -> int:
    """'YYYYMMDD' + New York saati → UTC epoch ms (yaz saati dahil)."""
    d = datetime(int(tarih[:4]), int(tarih[4:6]), int(tarih[6:8]), saat, dakika, tzinfo=NY)
    return int(d.timestamp() * 1000)


def fomc_tarihleri(sayfa: str) -> list[str]:
    return sorted(set(re.findall(r"pressreleases/monetary(\d{8})a\.htm", sayfa)))


def bls_tarihleri(sayfa: str, ad: str) -> list[str]:
    """Arşiv dosya adları MMDDYYYY → YYYYMMDD."""
    return sorted({f"{x[4:]}{x[:4]}" for x in re.findall(rf"archives/{ad}_(\d{{8}})\.htm", sayfa)})


def _persembe_tatili(g: date) -> bool:
    """Perşembeye denk gelen federal tatil (gözlenen gün kayması perşembeyi etkilemez: yalnız cuma/pazartesi)."""
    if (g.month, g.day) in {(1, 1), (7, 4), (11, 11), (12, 25)}:
        return True
    if (g.month, g.day) == (6, 19) and g.year >= 2021:
        return True
    return g.month == 11 and 22 <= g.day <= 28   # Kasım'ın dördüncü perşembesi: Şükran Günü


YAYIMLANMADI = ((date(2025, 10, 1), date(2025, 11, 13)),)   # hükümet kapanması (13 Kasım: belirsiz, temkinle dışarıda)


def issizlik_tarihleri(bas: date, bit: date) -> list[str]:
    """Haftalık işsizlik başvurularının yayın günleri (YYYYMMDD), [bas, bit]."""
    g = bas + timedelta(days=(3 - bas.weekday()) % 7)   # ilk perşembe
    out = []
    while g <= bit:
        y = g - timedelta(days=1) if _persembe_tatili(g) else g
        if not any(a <= y <= b for a, b in YAYIMLANMADI):
            out.append(y.strftime("%Y%m%d"))
        g += timedelta(days=7)
    return out


PLANLI_FOMC = Path(__file__).resolve().parents[3] / "config" / "fomc_planli.yaml"


def planli_fomc(yol: Path = PLANLI_FOMC) -> list[str]:
    """Önceden ilan edilmiş FOMC karar günleri (YYYYMMDD). Karar metni bağlantısı yalnız GEÇMİŞ toplantılar için var:
    bunlar olmadan canlı haber filtresi yaklaşan toplantıyı görmezdi (2026-10-18 denetimi: son FOMC 2026-09-16'ydı)."""
    if not yol.exists():
        return []
    return sorted(str(g) for g in yaml.safe_load(yol.read_text(encoding="utf-8"))["gunler"])


def olaylar(fomc_sayfa: str, nfp_sayfa: str, cpi_sayfa: str, ppi_sayfa: str = "",
            issizlik: tuple[date, date] | None = None, planli: list[str] | None = None) -> list[dict]:
    gecmis = fomc_tarihleri(fomc_sayfa)
    son = max(gecmis) if gecmis else ""
    ileri = [t for t in (planli or []) if t > son]      # yalnız son karar metninden SONRAKİ ilan edilmiş toplantılar
    out = [{"olay": "FOMC", "tarih": t, "utc_ms": ny_ms(t, 14, 0)} for t in gecmis + ileri]
    out += [{"olay": "NFP", "tarih": t, "utc_ms": ny_ms(t, 8, 30)} for t in bls_tarihleri(nfp_sayfa, "empsit")]
    out += [{"olay": "CPI", "tarih": t, "utc_ms": ny_ms(t, 8, 30)} for t in bls_tarihleri(cpi_sayfa, "cpi")]
    out += [{"olay": "PPI", "tarih": t, "utc_ms": ny_ms(t, 8, 30)} for t in bls_tarihleri(ppi_sayfa, "ppi")]
    if issizlik:
        out += [{"olay": "ISSIZLIK", "tarih": t, "utc_ms": ny_ms(t, 8, 30)} for t in issizlik_tarihleri(*issizlik)]
    return sorted(out, key=lambda o: (o["utc_ms"], o["olay"]))


def indir(ham: HamDepo, http: NazikIstemci | None = None, cikti: Path = CIKTI) -> dict:
    http = http or NazikIstemci("haber_takvimi", aralik_sn=2.0)
    sayfalar = {}
    for ad, url in (("fomc", FOMC), ("empsit", BLS.format("empsit")), ("cpi", BLS.format("cpi")),
                    ("ppi", BLS.format("ppi"))):
        icerik = http.al(url)
        _, sha, _ = ham.kaydet("haber_takvimi", f"{ad}/{datetime.now().date().isoformat()}", icerik, "html")
        sayfalar[ad] = (icerik.decode("utf-8", "ignore"), sha)
    ol = olaylar(sayfalar["fomc"][0], sayfalar["empsit"][0], sayfalar["cpi"][0], sayfalar["ppi"][0],
                 (date(2008, 1, 1), date(datetime.now().year + 1, 12, 31)), planli_fomc())
    # Sayfa yapısı değişir ya da engellenirse regex az eşleşir: commit'li takvim sessizce eksik haliyle ezilmesin.
    eski = {k: len(v) for k, v in _turlere(yukle_turlu(cikti)).items()}
    yeni = {k: sum(o["olay"] == k for o in ol) for k in TURLER}
    az = {k: (eski[k], yeni[k]) for k in eski if yeni.get(k, 0) < 0.95 * eski[k]}
    if az:
        raise RuntimeError(f"haber takvimi eksik geldi (eski, yeni): {az}; dosya değiştirilmedi")
    belge = {"aciklama": "Yüksek etkili ABD verileri (haber filtresi). Üreten: tradebot veri haber-takvimi",
             "kaynak_sha": {k: v[1] for k, v in sayfalar.items()}, "olaylar": ol}
    cikti.write_text(yaml.safe_dump(belge, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    return {k: sum(o["olay"] == k for o in ol) for k in TURLER}


TURLER = ("FOMC", "NFP", "CPI", "PPI", "ISSIZLIK")


def _turlere(liste: list[tuple[str, int]]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for tur, t in liste:
        out.setdefault(tur, []).append(t)
    return out
FILTRE_TURLERI = ("FOMC", "NFP", "CPI")   # Altın M15 haber filtresi (ön kayıt 2026-09-27)


def yukle_turlu(yol: Path = CIKTI, turler: tuple[str, ...] = TURLER) -> list[tuple[str, int]]:
    """(olay türü, UTC ms) sıralı."""
    if not yol.exists():
        return []
    ol = yaml.safe_load(yol.read_text(encoding="utf-8"))["olaylar"]
    return sorted(((o["olay"], int(o["utc_ms"])) for o in ol if o["olay"] in turler), key=lambda x: (x[1], x[0]))


def yukle(yol: Path = CIKTI, turler: tuple[str, ...] = FILTRE_TURLERI) -> list[int]:
    """Olay anları (UTC ms, sıralı). Varsayılan yalnız FOMC/NFP/CPI: haber filtresinin ön kaydı."""
    return sorted(ms for _, ms in yukle_turlu(yol, turler))
