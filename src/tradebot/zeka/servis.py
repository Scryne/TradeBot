"""Zekâ servisi: toplayıcılar → roller → olaylar. Tek tur `tur()`, servis döngüsü CLI'dan (`tradebot zeka calis`).

Çökme güvenliği: bir metin, adaylarından biri için bile yargı yoksa "işlenmemiş" sayılır ve sonraki turda yeniden ele
alınır; yargısı olan (metin, varlık) çifti tekrar sorulmaz.
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.engine import Engine

from tradebot.db import enstruman, jev_yargi, metin
from tradebot.db import olay as olay_t
from tradebot.kayit import log
from tradebot.metin.binance_duyuru import BinanceDuyuru
from tradebot.veri.depo import HamDepo
from tradebot.zeka import a1_binance as a1
from tradebot.zeka import olay
from tradebot.zeka.jev import JevIstemci
from tradebot.zeka.yukseltme import Yukseltme

AYAR_YOLU = Path(__file__).resolve().parents[3] / "config" / "zeka.yaml"
CANLI_PENCERE_MS = 10 * 60_000
_log = log("zeka.servis")


def ayar_oku(yol: Path = AYAR_YOLU) -> dict:
    return yaml.safe_load(Path(yol).read_text(encoding="utf-8"))


def binance_bazlari(motor: Engine) -> set[str]:
    with motor.connect() as b:
        ks = b.execute(select(enstruman.c.kimlik).where(enstruman.c.piyasa == "BINANCE")).scalars()
        return {k.removeprefix("BINANCE:").removesuffix("USDT") for k in ks if k.endswith("USDT")}


class Zeka:
    def __init__(self, motor: Engine, jev: JevIstemci, yukseltme: Yukseltme, toplayici: BinanceDuyuru, ayar: dict) -> None:
        self.motor, self.jev, self.yuk, self.top, self.ayar = motor, jev, yukseltme, toplayici, ayar

    def _sorulmus(self, metin_id: int) -> set[str]:
        with self.motor.connect() as b:
            hedefler = b.execute(select(jev_yargi.c.hedef).where(
                jev_yargi.c.rol == a1.ROL, jev_yargi.c.saglayici == "jev", jev_yargi.c.hata.is_(None),  # hatalı çağrı yeniden
                jev_yargi.c.hedef.like(f"metin:{metin_id}|%"))).scalars()
            return {h.split("|", 1)[1] for h in hedefler}

    def a1_metin(self, m, bazlar: set[str], simdi_ms: int) -> list[int]:
        """Bir Binance duyurusunu A1 ile değerlendirir. Döndürür: yazılan olay id'leri."""
        esik = float(self.ayar["jev"]["esik"])
        sorulmus = self._sorulmus(m.id)
        canli = simdi_ms - m.yayin_ms < CANLI_PENCERE_MS
        gecerli = simdi_ms if canli else m.yayin_ms + olay.GERIYE_DONUK_GECIKME_MS
        olaylar = []
        for varlik in a1.adaylar(m.baslik, m.govde, bazlar):
            kimlik = f"BINANCE:{varlik}USDT"
            if kimlik in sorulmus:
                continue
            st = a1.state(m.baslik, m.govde, varlik)
            hedef = f"metin:{m.id}|{kimlik}"
            y = self.jev.sor(a1.ROL, hedef, st, a1.SORULAR)
            secim, guven, p = y.secim("etki")
            yuk, yuk_model = (None, None)
            if y.hata or guven < esik:
                yuk, yuk_model = self.yuk.sec(a1.ROL, hedef, a1.ETKI.model_dump(mode="json"), st, "etki")
            veto, neden = a1.karar(None if y.hata else secim, guven, p, yuk, self.yuk.hazir, esik)
            belirsiz = neden.startswith("belirsiz")
            ayrinti = {"jev": secim, "guven": guven, "yukseltme": yuk, "yukseltme_model": yuk_model, "canli": canli,
                       "aciliyet": (y.cevap.get("aciliyet") or {}).get("score"), "baslik": m.baslik[:200]}
            if veto:
                olaylar.append(olay.yaz(self.motor, "veto", kimlik, gecerli, f"A1 {neden}: {m.baslik[:200]}", a1.ROL,
                                        m.id, y.id, None, ayrinti))
            if belirsiz:
                olaylar.append(olay.yaz(self.motor, "uyari", kimlik, gecerli, f"A1 belirsiz karar: {neden}", a1.ROL,
                                        m.id, y.id, None, ayrinti))
                _log.warning("a1_belirsiz", enstruman=kimlik, neden=neden)
            if veto:
                _log.info("a1_veto", enstruman=kimlik, neden=neden, canli=canli)
        return olaylar

    def belirsizleri_yukselt(self) -> dict:
        """Yükseltme modeli yokken belirsiz kalan A1 kararlarını yükseltme modeline sorar. Yalnız veto EKLER.

        Belirsiz yoldan önceden yazılmış veto, yükseltme "veto gerekmez" dese de kalır: kaldırmak riski artırır
        (kural 5/7). Yeni vetonun geçerlilik anı: geçmiş duyuruda uyarınınki (yayın + gecikme), canlıda şimdi.
        Başarılı yükseltmesi olan (metin, varlık) çifti tekrar sorulmaz.
        """
        if not self.yuk.hazir:
            return {"hazir": False}
        simdi = int(time.time() * 1000)
        with self.motor.connect() as b:
            uyarilar = list(b.execute(select(olay_t).where(olay_t.c.tur == "uyari", olay_t.c.rol == a1.ROL)
                                      .order_by(olay_t.c.id)))
            vetolu = {(r.metin_id, r.enstruman) for r in b.execute(select(olay_t.c.metin_id, olay_t.c.enstruman).where(
                olay_t.c.tur == "veto", olay_t.c.rol == a1.ROL))}
            yukseltilmis = set(b.execute(select(jev_yargi.c.hedef).where(
                jev_yargi.c.rol == a1.ROL, jev_yargi.c.saglayici == "nvidia", jev_yargi.c.hata.is_(None))).scalars())
        sayac = {"hazir": True, "yukseltildi": 0, "yeni_veto": 0, "korunan_veto": 0, "basarisiz": 0}
        for u in uyarilar:
            if (u.ayrinti or {}).get("yukseltme") is not None:
                continue
            hedef = f"metin:{u.metin_id}|{u.enstruman}"
            if hedef in yukseltilmis:
                continue
            with self.motor.connect() as b:
                m = b.execute(select(metin).where(metin.c.id == u.metin_id)).one()
            varlik = u.enstruman.removeprefix("BINANCE:").removesuffix("USDT")
            secim, model = self.yuk.sec(a1.ROL, hedef, a1.ETKI.model_dump(mode="json"), a1.state(m.baslik, m.govde, varlik),
                                        "etki")
            if secim is None:
                sayac["basarisiz"] += 1
                continue
            yukseltilmis.add(hedef)
            sayac["yukseltildi"] += 1
            if secim not in a1.VETO:
                sayac["korunan_veto"] += (u.metin_id, u.enstruman) in vetolu
                continue
            if (u.metin_id, u.enstruman) in vetolu:
                continue
            gecerli = simdi if (u.ayrinti or {}).get("canli") else u.gecerli_ms
            olay.yaz(self.motor, "veto", u.enstruman, gecerli, f"A1 yukseltme:{secim} ({model}): {m.baslik[:200]}",
                     a1.ROL, u.metin_id, u.yargi_id, None, {**(u.ayrinti or {}), "yukseltme": secim,
                                                            "yukseltme_model": model, "sonradan": True})
            vetolu.add((u.metin_id, u.enstruman))
            sayac["yeni_veto"] += 1
        return sayac

    def son_metinler(self, sinir: int | None = 200) -> list:
        """Son `sinir` Binance duyurusu; her turda taranır, yargısı olan (metin, varlık) çifti atlanır."""
        with self.motor.connect() as b:
            q = select(metin).where(metin.c.kaynak == "binance_duyuru").order_by(metin.c.yayin_ms.desc())
            return list(b.execute(q.limit(sinir) if sinir else q))

    def tur(self, sayfa_sayisi: int = 1, kataloglar: list[int] | None = None, metin_siniri: int | None = 200) -> dict:
        yeni = self.top.topla(kataloglar or self.ayar["binance"]["kataloglar"], sayfa_sayisi)
        bazlar = binance_bazlari(self.motor)
        simdi = int(time.time() * 1000)
        olaylar = []
        for m in reversed(self.son_metinler(metin_siniri)):  # eskiden yeniye
            olaylar += self.a1_metin(m, bazlar, simdi)
        return {"yeni_metin": len(yeni), "olay": len(olaylar)}


def kur(motor: Engine, a, ayar: dict | None = None) -> Zeka:
    """Ayarlar (sırlar) + config/zeka.yaml → çalışır servis. Anahtarlar yalnız ortamdan (kural 12)."""
    ayar = ayar or ayar_oku()
    jev = JevIstemci(motor, ayar["jev"]["model"],
                     api_key=a.typesafe_api_key.get_secret_value() if a.typesafe_api_key else None)
    y = ayar["yukseltme"]
    yuk = Yukseltme(motor, y["base_url"], list(y.get("modeller") or []),
                    a.nvidia_api_key.get_secret_value() if a.nvidia_api_key else None,
                    zaman_asimi=float(y.get("zaman_asimi_sn", 120)))
    return Zeka(motor, jev, yuk, BinanceDuyuru(HamDepo(a.veri_dizini, motor), motor), ayar)
