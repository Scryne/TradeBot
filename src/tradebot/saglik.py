"""Sağlık kontrolleri: host ve konteyner ortamının Faz 1 şartlarını karşıladığını doğrular.

- DNS: kritik alan adlarının çözümleme süresi (Spike 02/03: ev router'ında 5–15 sn → konteyner DNS'i 1.1.1.1).
- Saat: NTP (SNTP) ve Binance sunucu saatine göre yerel saat kayması (Spike 02: 1 sn geride).
- Veritabanı: bağlantı + denetim izi zincirinin sağlamlığı.
- Disk: veri dizininde boş alan.
- Sırlar: tanımlı mı (değerleri asla yazılmaz).

Her kontrol OK / UYARI / HATA döndürür; komut en kötü duruma göre çıkış kodu verir.
"""
from __future__ import annotations

import json
import shutil
import socket
import struct
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from tradebot.ayar import SIR_ALANLARI, Ayarlar

KRITIK_ADLAR = (
    "api.binance.com", "stream.binance.com", "data.binance.vision", "datafeed.dukascopy.com",
    "query1.finance.yahoo.com", "www.kap.org.tr", "data.sec.gov", "api.typesafe.ai",
)
NTP_SUNUCULARI = ("time.cloudflare.com", "pool.ntp.org")
_NTP_DELTA = 2_208_988_800  # 1900-01-01 → 1970-01-01 saniye


@dataclass
class Sonuc:
    ad: str
    durum: str  # OK | UYARI | HATA
    ayrinti: str
    olcum: dict = field(default_factory=dict)


def _sinifla(deger: float, uyari: float, hata: float) -> str:
    return "OK" if deger < uyari else ("UYARI" if deger < hata else "HATA")


def dns_kontrol(a: Ayarlar, adlar: tuple[str, ...] = KRITIK_ADLAR) -> Sonuc:
    sureler: dict[str, float] = {}
    hatalar = []
    for ad in adlar:
        t0 = time.perf_counter()
        try:
            socket.getaddrinfo(ad, 443)
            sureler[ad] = round(time.perf_counter() - t0, 2)
        except OSError as e:
            hatalar.append(f"{ad}: {e}")
    if hatalar:
        return Sonuc("dns", "HATA", "; ".join(hatalar), sureler)
    en_kotu = max(sureler, key=sureler.get)
    durum = _sinifla(sureler[en_kotu], a.dns_uyari_sn, a.dns_hata_sn)
    return Sonuc("dns", durum, f"en yavaş {en_kotu} {sureler[en_kotu]} sn", sureler)


def sntp_paketi_coz(paket: bytes, t_gonder: float, t_al: float) -> float:
    """SNTP yanıtından saat farkını (sunucu − yerel, sn) hesaplar (RFC 4330)."""
    if len(paket) < 48:
        raise ValueError("kısa NTP paketi")
    alim_sn, alim_kesir, iletim_sn, iletim_kesir = struct.unpack("!II II", paket[32:48])
    t2 = alim_sn - _NTP_DELTA + alim_kesir / 2**32
    t3 = iletim_sn - _NTP_DELTA + iletim_kesir / 2**32
    return ((t2 - t_gonder) + (t3 - t_al)) / 2


def ntp_fark(sunucu: str, zaman_asimi: float = 3.0) -> float:
    istek = b"\x1b" + 47 * b"\0"  # LI=0, VN=3, Mode=3 (istemci)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(zaman_asimi)
        t1 = time.time()
        s.sendto(istek, (sunucu, 123))
        paket, _ = s.recvfrom(512)
        t4 = time.time()
    return sntp_paketi_coz(paket, t1, t4)


def binance_fark(zaman_asimi: float = 5.0) -> float:
    t1 = time.time()
    with urllib.request.urlopen("https://api.binance.com/api/v3/time", timeout=zaman_asimi) as r:
        sunucu = json.load(r)["serverTime"] / 1000
    t4 = time.time()
    return sunucu - (t1 + t4) / 2


def saat_kontrol(a: Ayarlar) -> Sonuc:
    olcum: dict[str, float] = {}
    for s in NTP_SUNUCULARI:
        try:
            olcum[f"ntp:{s}"] = round(ntp_fark(s), 3)
            break
        except OSError:
            continue
    try:
        olcum["binance"] = round(binance_fark(), 3)
    except OSError:
        pass
    if not olcum:
        return Sonuc("saat", "HATA", "hiçbir zaman kaynağına ulaşılamadı")
    en_kotu = max(olcum, key=lambda k: abs(olcum[k]))
    fark = abs(olcum[en_kotu])
    return Sonuc("saat", _sinifla(fark, a.saat_uyari_sn, a.saat_hata_sn),
                 f"en büyük kayma {en_kotu} {olcum[en_kotu]:+.3f} sn (pozitif: yerel saat geride)", olcum)


def veritabani_kontrol(a: Ayarlar) -> Sonuc:
    if a.veritabani_url is None:
        return Sonuc("veritabani", "UYARI", "TRADEBOT_VERITABANI_URL tanımlı değil (yalnız geliştirmede kabul)")
    from sqlalchemy import text

    from tradebot import denetim
    from tradebot.db import motor

    try:
        m = motor(a)
        with m.connect() as b:
            surum = b.execute(text("SELECT version()")).scalar() if m.dialect.name == "postgresql" else m.dialect.name
        saglam, kirik, n = denetim.dogrula(m)
    except Exception as e:  # bağlantı ya da şema hatası
        return Sonuc("veritabani", "HATA", f"{type(e).__name__}: {e}"[:200])
    if not saglam:
        return Sonuc("veritabani", "HATA", f"denetim izi zinciri {kirik} numaralı kayıtta kırık", {"kayit": n})
    return Sonuc("veritabani", "OK", f"{str(surum)[:40]} · denetim izi {n} kayıt, zincir sağlam", {"kayit": n})


def disk_kontrol(a: Ayarlar) -> Sonuc:
    yol = Path(a.veri_dizini)
    yol.mkdir(parents=True, exist_ok=True)
    bos_gb = shutil.disk_usage(yol).free / 1e9
    durum = "OK" if bos_gb >= a.disk_uyari_gb else ("UYARI" if bos_gb >= a.disk_uyari_gb / 5 else "HATA")
    return Sonuc("disk", durum, f"{yol.resolve()} boş {bos_gb:.0f} GB", {"bos_gb": round(bos_gb, 1)})


def sir_kontrol(a: Ayarlar) -> Sonuc:
    tanimli = {ad: getattr(a, ad) is not None for ad in SIR_ALANLARI}
    eksik = [ad for ad, v in tanimli.items() if not v]
    durum = "OK" if not eksik else "UYARI"
    return Sonuc("sirlar", durum, "tümü tanımlı" if not eksik else f"tanımsız: {', '.join(eksik)}", tanimli)


def hepsi(a: Ayarlar) -> list[Sonuc]:
    return [f(a) for f in (dns_kontrol, saat_kontrol, veritabani_kontrol, disk_kontrol, sir_kontrol)]


def cikis_kodu(sonuclar: list[Sonuc]) -> int:
    durumlar = {s.durum for s in sonuclar}
    return 2 if "HATA" in durumlar else (1 if "UYARI" in durumlar else 0)
