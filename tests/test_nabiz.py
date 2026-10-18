""""Habere kör" mod (risk katmanı 5): zekâ nabzı ve yeni girişin yarım boyuta inmesi."""
import numpy as np
import pytest

from tradebot.canli import karar as kr
from tradebot.zeka import nabiz

SIMDI = 1_790_608_000_000
DK = 60_000


def test_kor_hedef_yalniz_yeni_riski_yariya_indirir():
    hedef = np.array([0.4, 0.4, 0.4, -0.4, 0.0, 0.2])
    kaymis = np.array([0.0, 0.3, 0.5, 0.3, 0.3, 0.1])
    h = kr.habere_kor_hedef(hedef, kaymis)
    # yeni giriş yarım · mevcut korunur, büyütülmez · azaltma serbest · yön değişimi: yeni taraf yarım · kapatma serbest
    # · mevcut hedefin yarısından büyükse aynen kalır
    assert h == pytest.approx([0.2, 0.3, 0.4, -0.2, 0.0, 0.1])
    assert np.all(np.abs(h) <= np.abs(hedef) + 1e-12) and np.all(np.sign(h) * np.sign(hedef) >= 0)
    assert kr.habere_kor_hedef(h, h) == pytest.approx(h * 0 + np.where(np.abs(h) > 0, h, 0))  # vardıktan sonra sabit


def test_karar_kor_modu_yalniz_jevli_kopyada(tmp_path):
    import dataclasses

    from tests.test_canli import KAYIT, kol_yap, sentetik_depo
    from tradebot.canli import karar as kr2

    depo, t = sentetik_depo(tmp_path)
    kol = dataclasses.replace(kol_yap(), baslangic_ozkaynak=100_000.0)
    jev = dataclasses.replace(kol, ad=kol.ad + "+jev", ayar=dataclasses.replace(kol.ayar, jev_veto=True))
    assert jev.jev and not kol.jev
    kapanis = int(t[-1]) + 3_600_000
    h = kr2.hazirla(depo, KAYIT, kol, bit_ms=kapanis)
    hedef = np.array([0.4, 0.3])
    tam = kr2.karar_ver(jev, h, kr2.KolDurum(ozkaynak=100_000.0, nakit=100_000.0), set(), hedef)
    kor = kr2.karar_ver(jev, h, kr2.KolDurum(ozkaynak=100_000.0, nakit=100_000.0), set(), hedef, habere_kor=True)
    jevsiz = kr2.karar_ver(kol, h, kr2.KolDurum(ozkaynak=100_000.0, nakit=100_000.0), set(), hedef, habere_kor=True)
    assert kor.habere_kor and not jevsiz.habere_kor
    assert kor.yeni == pytest.approx(tam.yeni * 0.5)
    assert jevsiz.yeni == pytest.approx(tam.yeni)


def test_nabiz_kor_durumlari(tmp_path):
    assert nabiz.kor_mu(tmp_path, SIMDI) == (True, "nabız yok")
    nabiz.yaz(tmp_path, SIMDI, {"binance_duyuru", "kap"}, SIMDI - DK, None)
    assert nabiz.kor_mu(tmp_path, SIMDI + DK) == (False, "")
    assert nabiz.kor_mu(tmp_path, SIMDI + 20 * DK)[0]                        # servis tur atmıyor
    nabiz.yaz(tmp_path, SIMDI + 20 * DK, {"kap"}, SIMDI, None)             # Binance 20 dk'dır çekilemiyor
    assert nabiz.kor_mu(tmp_path, SIMDI + 20 * DK) == (True, "binance_duyuru çekilemiyor")
    assert not nabiz.kor_mu(tmp_path, SIMDI + 20 * DK, kaynak="kap")[0]       # düğümün kendi kaynağı tazeyse kör değil
    nabiz.yaz(tmp_path, SIMDI + 21 * DK, {"binance_duyuru"}, SIMDI, SIMDI + 21 * DK)   # son Jev çağrısı hatalı
    assert nabiz.kor_mu(tmp_path, SIMDI + 21 * DK) == (True, "son Jev çağrısı hatalı")
    nabiz.yaz(tmp_path, SIMDI + 22 * DK, {"binance_duyuru"}, SIMDI + 22 * DK, SIMDI + 21 * DK)
    assert nabiz.kor_mu(tmp_path, SIMDI + 22 * DK) == (False, "")
    (tmp_path / nabiz.DOSYA).write_text("{bozuk", encoding="utf-8")
    assert nabiz.kor_mu(tmp_path, SIMDI)[0]                                  # okunamazsa kör (belirsizlikte riski azalt)
