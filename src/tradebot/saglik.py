"""Sağlık kontrolleri: host ve konteyner ortamının Faz 1 şartlarını karşıladığını doğrular.

- DNS: kritik alan adlarının çözümleme süresi (Spike 02/03: ev router'ında 5–15 sn → konteyner DNS'i 1.1.1.1).
- Saat: NTP (SNTP) ve Binance sunucu saatine göre yerel saat kayması (Spike 02: 1 sn geride).
- Veritabanı: bağlantı + denetim izi zincirinin sağlamlığı.
- Disk: veri dizininde boş alan.
- Sırlar: tanımlı mı (değerleri asla yazılmaz).
- Bekçi (host'ta, 2026-09-27 denetimi): paper düğümünün kalp atışı (saatlik özkaynak işareti), gece işinin son kaydı,
  veritabanı yedeğinin yaşı; `LogTriyaj` servis loglarındaki yeni hata satırlarını toplar. `saglik --dongu` bunları
  durum değişiminde Telegram'a bildirir (`bildirim.py`). Motordan bağımsız süreçtir: paper donarsa bekçi görür.

Her kontrol OK / UYARI / HATA döndürür; komut en kötü duruma göre çıkış kodu verir.
"""
from __future__ import annotations

import http.client
import json
import shutil
import socket
import struct
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    adres = socket.getaddrinfo(sunucu, 123, socket.AF_INET, socket.SOCK_DGRAM)[0][4]  # DNS t1–t4 penceresine girmesin
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(zaman_asimi)
        t1 = time.time()
        s.sendto(istek, adres)
        paket, _ = s.recvfrom(512)
        t4 = time.time()
    return sntp_paketi_coz(paket, t1, t4)


def en_kisa_gidis_donus(ornekler: list[tuple[float, float, float]]) -> float:
    """(t1, sunucu, t4) örneklerinden gidiş-dönüşü en kısa olanın farkı. Orta nokta varsayımının hatası en fazla
    gidiş-dönüşün yarısıdır; en kısa örnek en az hatalı olandır (NTP'nin de yolu)."""
    t1, sunucu, t4 = min(ornekler, key=lambda o: o[2] - o[0])
    return sunucu - (t1 + t4) / 2


def binance_fark(zaman_asimi: float = 5.0, ornek: int = 3) -> float:
    """Açık bağlantı üzerinden ölçülür. Eskiden t1 bağlantı kurulmadan alınıyordu: DNS + TCP + TLS süresi pencereye
    giriyor, sunucu damgası pencerenin sonunda kaldığı için kayma hep pozitif çıkıyordu (host'ta DNS yavaşken +2,1 sn
    HATA, 5 dk sonra +0,1 sn; 2026-09-27)."""
    b = http.client.HTTPSConnection("api.binance.com", timeout=zaman_asimi)
    try:
        b.connect()
        ornekler = []
        for _ in range(ornek):
            t1 = time.time()
            b.request("GET", "/api/v3/time")
            sunucu = json.loads(b.getresponse().read())["serverTime"] / 1000
            ornekler.append((t1, sunucu, time.time()))
    finally:
        b.close()
    return en_kisa_gidis_donus(ornekler)


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


def _yas_sinifla(ad: str, yas_sn: float | None, uyari_sn: float, hata_sn: float, ne: str) -> Sonuc:
    if yas_sn is None:
        return Sonuc(ad, "HATA", f"{ne} hiç yok")
    dk = yas_sn / 60
    metin = f"son {ne} {dk:.0f} dk önce" if dk < 180 else f"son {ne} {dk / 60:.1f} saat önce"
    return Sonuc(ad, _sinifla(yas_sn, uyari_sn, hata_sn), metin, {"yas_sn": round(yas_sn)})


def paper_kontrol(a: Ayarlar, simdi_ms: int | None = None, dugum: str = "paper") -> Sonuc:
    """Kalp atışı: paper düğümü her saat kapanışında özkaynak işareti yazar. > 70 dk uyarı, > 2 saat hata. Düğüm başına
    (gozetmen.dugum_kollari): kilit düğümünün saatlik işareti Nautilus düğümünün donmasını gizlemez."""
    from tradebot.canli.gozetmen import son_isaret_ms
    from tradebot.db import motor

    try:
        son = son_isaret_ms(motor(a), dugum)
    except Exception as e:  # noqa: BLE001
        return Sonuc(dugum, "HATA", f"{type(e).__name__}: {e}"[:200])
    simdi_ms = simdi_ms or int(time.time() * 1000)
    return _yas_sinifla(dugum, None if son is None else (simdi_ms - son) / 1000, 70 * 60, 120 * 60, "özkaynak işareti")


def kilit_kontrol(a: Ayarlar, simdi_ms: int | None = None) -> Sonuc:
    """Kilit düğümünün kalp atışı (canli/kilit.py, saatte bir işaret). Kol henüz açılmadıysa bilgi: çalışmıyor."""
    from tradebot.canli.gozetmen import dugum_kollari
    from tradebot.db import motor

    try:
        if not dugum_kollari(motor(a)).get("kilit"):
            return Sonuc("kilit", "OK", "kilit kolu henüz açılmadı")
    except Exception as e:  # noqa: BLE001
        return Sonuc("kilit", "HATA", f"{type(e).__name__}: {e}"[:200])
    return paper_kontrol(a, simdi_ms, "kilit")


def doviz_kontrol(a: Ayarlar, simdi_ms: int | None = None) -> Sonuc:
    """Döviz düğümünün kalp atışı (canli/doviz.py, saatte bir işaret). Kol henüz açılmadıysa bilgi."""
    from tradebot.canli.gozetmen import dugum_kollari
    from tradebot.db import motor

    try:
        if not dugum_kollari(motor(a)).get("doviz"):
            return Sonuc("doviz", "OK", "döviz kolu henüz açılmadı")
    except Exception as e:  # noqa: BLE001
        return Sonuc("doviz", "HATA", f"{type(e).__name__}: {e}"[:200])
    return paper_kontrol(a, simdi_ms, "doviz")


def altin_kontrol(a: Ayarlar, simdi_ms: int | None = None) -> Sonuc:
    """Altın M15 düğümünün kalp atışı (canli/altin.py, saatte bir işaret). Kol henüz açılmadıysa bilgi."""
    from tradebot.canli.gozetmen import dugum_kollari
    from tradebot.db import motor

    try:
        if not dugum_kollari(motor(a)).get("altin"):
            return Sonuc("altin", "OK", "altın kolu henüz açılmadı")
    except Exception as e:  # noqa: BLE001
        return Sonuc("altin", "HATA", f"{type(e).__name__}: {e}"[:200])
    return paper_kontrol(a, simdi_ms, "altin")


def gece_kontrol(a: Ayarlar, simdi: datetime | None = None) -> Sonuc:
    """Gece işi her gün 01:30 UTC'de `gece_isi` denetim kaydı yazar. > 26 saat uyarı, > 50 saat hata."""
    from sqlalchemy import func, select

    from tradebot.db import denetim_izi, motor

    try:
        with motor(a).connect() as b:
            son = b.execute(select(func.max(denetim_izi.c.zaman)).where(denetim_izi.c.olay == "gece_isi")).scalar()
    except Exception as e:  # noqa: BLE001
        return Sonuc("gece_isi", "HATA", f"{type(e).__name__}: {e}"[:200])
    simdi = simdi or datetime.now(UTC)
    yas = None if son is None else (simdi - (son if son.tzinfo else son.replace(tzinfo=UTC))).total_seconds()
    return _yas_sinifla("gece_isi", yas, 26 * 3600, 50 * 3600, "gece işi kaydı")


def yedek_kontrol(a: Ayarlar, simdi: datetime | None = None) -> Sonuc:
    """compose `yedek`in son.json'u: > 26 saat ya da daha yeni bir hata kaydı → HATA."""
    d = Path(a.yedek_dizini)
    simdi = simdi or datetime.now(UTC)
    try:
        son = json.loads((d / "son.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Sonuc("yedek", "HATA", f"{d / 'son.json'} okunamadı (hiç yedek alınmamış olabilir)")
    zaman = datetime.fromisoformat(son["zaman"].replace("Z", "+00:00"))
    hata = d / "son_hata.json"
    if hata.exists():
        hz = datetime.fromisoformat(json.loads(hata.read_text(encoding="utf-8"))["zaman"].replace("Z", "+00:00"))
        if hz > zaman:
            return Sonuc("yedek", "HATA", f"son yedek denemesi başarısız ({hz:%Y-%m-%d %H:%M} UTC)")
    r = _yas_sinifla("yedek", (simdi - zaman).total_seconds(), 26 * 3600, 26 * 3600, "yedek")
    r.ayrinti += f" · {son['dosya']} {son['bayt'] / 1e6:.0f} MB"
    return r


class LogTriyaj:
    """Log dizinindeki *.jsonl dosyalarının YENİ satırlarından hata olayları. İlk bakışta dosya sonundan başlar (geçmiş
    hatalar yeniden bildirilmez); dönen dosyada (boyut küçüldü) baştan okur."""

    def __init__(self, dizin: Path) -> None:
        self.dizin = Path(dizin)
        self.konum: dict[Path, int] | None = None

    def yeni_hatalar(self) -> list[dict]:
        dosyalar = sorted(self.dizin.glob("*.jsonl")) if self.dizin.exists() else []
        if self.konum is None:
            self.konum = {f: f.stat().st_size for f in dosyalar}
            return []
        out = []
        for f in dosyalar:
            boy = f.stat().st_size
            bas = self.konum.get(f, 0)
            if boy < bas:
                bas = 0
            if boy == bas:
                continue
            with f.open("rb") as fh:
                fh.seek(bas)
                parca = fh.read(boy - bas)
            son_satir = parca.rfind(b"\n") + 1   # yarım satırı sonraki tura bırak
            self.konum[f] = bas + son_satir
            for satir in parca[:son_satir].splitlines():
                try:
                    k = json.loads(satir)
                except ValueError:
                    continue
                if k.get("level") in ("error", "critical"):
                    out.append({"dosya": f.stem, "bilesen": k.get("bilesen"), "olay": k.get("event"),
                                "ozet": {x: v for x, v in k.items() if x not in ("event", "level", "bilesen")}})
        return out


KRITIK = ("paper", "kilit", "gece_isi", "yedek", "veritabani")
ORTAM = ("dns", "saat", "disk", "mt5")   # anlık dalgalanan ortam ölçümleri: bildirim için art arda onay ister
_AGIRLIK = {"OK": 0, "UYARI": 1, "HATA": 2}


class DurumIzleyici:
    """Bekçinin durum hafızası: ham durum her turda gelir, bildirim yalnız *onaylı* durum değişince gider.

    Ortam kontrolleri (DNS, saat, disk, MT5 köprüsü) son `onay` turun hepsi aynı yönde olunca değişir (histerezis):
    hepsi bildirilenden kötüyse içlerinden en iyisine yükselir, hepsi iyiyse en kötüsüne iner. UYARI/HATA arasında
    gidip gelen DNS UYARI olarak onaylanır, tek turluk sıçrama hiç bildirilmez. Kritik kontroller (paper, gece işi,
    yedek, veritabanı) ilk turda. Açılışta yalnız sorunlular bildirilir, düzelme yalnız bildirilmiş bir sorun için.
    Sırlar bildirilmez."""

    def __init__(self, onay: int = 3) -> None:
        self.onay = onay
        self.ham: dict[str, str] = {}
        self.pencere: dict[str, list[int]] = {}
        self.bildirilen: dict[str, str] = {}

    def isle(self, s: Sonuc) -> tuple[bool, bool]:
        """Döndürür: (ham durum değişti mi → log, onaylı durum değişti mi → bildirim)."""
        degisti = self.ham.get(s.ad) != s.durum
        self.ham[s.ad] = s.durum
        n = self.onay if s.ad in ORTAM else 1
        p = self.pencere.setdefault(s.ad, [])
        p.append(_AGIRLIK[s.durum])
        del p[:-n]
        if s.ad == "sirlar" or len(p) < n:
            return degisti, False
        onceki = _AGIRLIK[self.bildirilen.get(s.ad, "OK")]
        yeni = min(p) if min(p) > onceki else (max(p) if max(p) < onceki else onceki)
        if yeni == onceki:
            return degisti, False
        self.bildirilen[s.ad] = next(k for k, v in _AGIRLIK.items() if v == yeni)
        return degisti, True


def olu_adam(a: Ayarlar, sonuclar: list[Sonuc], zaman_asimi: float = 10.0) -> bool | None:
    """Dış "ölü adam" sinyali (healthchecks.io). Kritik bir kontrol HATA ise `/fail` (dış kanaldan da alarm), değilse
    başarı. Host tamamen kapanırsa sinyal kesilir ve dış servis alarm verir: bekçinin göremediği tek durum bu.
    Döndürür: gönderildi mi (None: adres tanımsız)."""
    if not a.olu_adam_url:
        return None
    hata = [s.ad for s in sonuclar if s.ad in KRITIK and s.durum == "HATA"]
    url = a.olu_adam_url.rstrip("/") + ("/fail" if hata else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=(", ".join(hata) or "ok").encode()),
                                    timeout=zaman_asimi) as r:
            return r.status == 200
    except OSError:
        return False


def hepsi(a: Ayarlar) -> list[Sonuc]:
    kontroller = [dns_kontrol, saat_kontrol, veritabani_kontrol, disk_kontrol, sir_kontrol]
    if a.ortam == "host" and a.veritabani_url is not None:
        kontroller += [paper_kontrol, kilit_kontrol, doviz_kontrol, altin_kontrol, gece_kontrol]
    if a.yedek_dizini is not None:
        kontroller.append(yedek_kontrol)
    if a.mt5_kopru_forex or a.mt5_kopru_viop:
        kontroller.append(mt5_kontrol)
    return [f(a) for f in kontroller]


def mt5_kontrol(a: Ayarlar) -> Sonuc:
    """MT5 köprüleri (Faz 8): ulaşılamayan ya da terminali bağlı olmayan köprü HATA. Piyasa kapalıyken taze tik
    olmaması normaldir (yalnız bilgi)."""
    from tradebot.mt5.istemci import KopruHatasi, Mt5Istemci

    parcalar, kotu, olcum = [], [], {}
    for hesap, url in (("forex", a.mt5_kopru_forex), ("viop", a.mt5_kopru_viop)):
        if not url:
            continue
        try:
            s = Mt5Istemci(url, zaman_asimi=15).saglik()
        except KopruHatasi as e:
            kotu.append(hesap)
            parcalar.append(f"{hesap}: {str(e)[:80]}")
            continue
        olcum[hesap] = s
        if not s["bagli"]:
            kotu.append(hesap)
        yas = s.get("taze_tik_yas_sn")
        parcalar.append(f"{hesap} {'bağlı' if s['bagli'] else 'BAĞLI DEĞİL'} · fark {s['fark_sn'] / 3600:+.1f} sa "
                        f"({s['fark_kaynak']})" + ("" if yas is None else f" · son taze tik {yas} sn önce"))
    return Sonuc("mt5", "HATA" if kotu else "OK", "; ".join(parcalar), olcum)


def cikis_kodu(sonuclar: list[Sonuc]) -> int:
    durumlar = {s.durum for s in sonuclar}
    return 2 if "HATA" in durumlar else (1 if "UYARI" in durumlar else 0)
