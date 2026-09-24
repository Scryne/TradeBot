import struct

import pytest

from tradebot import saglik


def _ntp_paketi(t2: float, t3: float) -> bytes:
    def ntp(t):
        s = int(t) + saglik._NTP_DELTA
        return s, int((t - int(t)) * 2**32)
    a, b = ntp(t2)
    c, d = ntp(t3)
    return b"\x1c" + b"\0" * 31 + struct.pack("!IIII", a, b, c, d)


def test_sntp_fark_hesabi():
    # yerel saat sunucudan 1,0 sn geride; ağ gecikmesi simetrik 0,1 sn
    t1 = 1000.0
    t2 = t1 + 1.0 + 0.1   # sunucu alış (sunucu saatiyle)
    t3 = t2 + 0.01        # sunucu gönderiş
    t4 = t1 + 0.21        # yerel alış
    fark = saglik.sntp_paketi_coz(_ntp_paketi(t2, t3), t1, t4)
    assert fark == pytest.approx(1.0, abs=1e-3)


def test_kisa_paket_hata():
    with pytest.raises(ValueError):
        saglik.sntp_paketi_coz(b"\0" * 10, 0, 0)


def test_siniflama_esikleri():
    assert saglik._sinifla(0.2, 1, 3) == "OK"
    assert saglik._sinifla(1.5, 1, 3) == "UYARI"
    assert saglik._sinifla(11.0, 1, 3) == "HATA"


def test_cikis_kodu():
    S = saglik.Sonuc
    assert saglik.cikis_kodu([S("a", "OK", "")]) == 0
    assert saglik.cikis_kodu([S("a", "OK", ""), S("b", "UYARI", "")]) == 1
    assert saglik.cikis_kodu([S("a", "UYARI", ""), S("b", "HATA", "")]) == 2


def test_veritabani_ve_sir_kontrolu(ayar):
    from tradebot.db import metadata, motor
    metadata.create_all(motor(ayar))
    s = saglik.veritabani_kontrol(ayar)
    assert s.durum == "OK" and "zincir sağlam" in s.ayrinti
    sir = saglik.sir_kontrol(ayar)
    assert sir.durum == "UYARI" and "typesafe_api_key" in sir.ayrinti
    assert "sqlite" not in str(sir.olcum)  # değer değil, yalnız var/yok


def test_disk(ayar):
    s = saglik.disk_kontrol(ayar)
    assert s.durum in {"OK", "UYARI", "HATA"} and s.olcum["bos_gb"] > 0
