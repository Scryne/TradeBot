"""Yüksek etkili ABD veri takvimi (haber filtresi için): FOMC kararı, tarım dışı istihdam (NFP), TÜFE (CPI).

Kaynaklar resmidir ve tarihler yayından önce ilan edilir (BLS yıllık takvim, Fed toplantı takvimi), yani filtre geleceği
görmez. Olağanüstü FOMC toplantıları ve ertelenen/iptal edilen BLS yayınları arşivde gerçekleştiği gibi durur.
- FOMC: federalreserve.gov/monetarypolicy/fomccalendars.htm → `pressreleases/monetaryYYYYMMDDa.htm` (karar metni),
  14:00 New York (2013'ten beri sabit saat).
- NFP / CPI: bls.gov/bls/news-release/{empsit,cpi}.htm arşivi → `archives/{empsit,cpi}_MMDDYYYY.htm`, 08:30 New York.
  BLS, tarayıcı taklidi yapan istemciye 403 veriyor; iletişim adresli dürüst User-Agent ile açılıyor (ölçüldü).
Çıktı: `config/haber_takvimi.yaml` (commit edilir; kaynak sayfaların hash'i ham depoda).
"""
from __future__ import annotations

import re
from datetime import datetime
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


def olaylar(fomc_sayfa: str, nfp_sayfa: str, cpi_sayfa: str) -> list[dict]:
    out = [{"olay": "FOMC", "tarih": t, "utc_ms": ny_ms(t, 14, 0)} for t in fomc_tarihleri(fomc_sayfa)]
    out += [{"olay": "NFP", "tarih": t, "utc_ms": ny_ms(t, 8, 30)} for t in bls_tarihleri(nfp_sayfa, "empsit")]
    out += [{"olay": "CPI", "tarih": t, "utc_ms": ny_ms(t, 8, 30)} for t in bls_tarihleri(cpi_sayfa, "cpi")]
    return sorted(out, key=lambda o: o["utc_ms"])


def indir(ham: HamDepo, http: NazikIstemci | None = None, cikti: Path = CIKTI) -> dict:
    http = http or NazikIstemci("haber_takvimi", aralik_sn=2.0)
    sayfalar = {}
    for ad, url in (("fomc", FOMC), ("empsit", BLS.format("empsit")), ("cpi", BLS.format("cpi"))):
        icerik = http.al(url)
        _, sha, _ = ham.kaydet("haber_takvimi", f"{ad}/{datetime.now().date().isoformat()}", icerik, "html")
        sayfalar[ad] = (icerik.decode("utf-8", "ignore"), sha)
    ol = olaylar(sayfalar["fomc"][0], sayfalar["empsit"][0], sayfalar["cpi"][0])
    belge = {"aciklama": "Yüksek etkili ABD verileri (haber filtresi). Üreten: tradebot veri haber-takvimi",
             "kaynak_sha": {k: v[1] for k, v in sayfalar.items()}, "olaylar": ol}
    cikti.write_text(yaml.safe_dump(belge, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    return {k: sum(o["olay"] == k for o in ol) for k in ("FOMC", "NFP", "CPI")}


def yukle(yol: Path = CIKTI) -> list[int]:
    """Olay anları (UTC ms, sıralı)."""
    if not yol.exists():
        return []
    return sorted(int(o["utc_ms"]) for o in yaml.safe_load(yol.read_text(encoding="utf-8"))["olaylar"])
