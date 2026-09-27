"""Paper defteri (PostgreSQL, yalnız eklenir): kolun doğruluk kaynağı.

Nautilus sandbox'ı bellektedir, yeniden başlatmada sıfırlanır. Kol durumu (nakit, adetler, önceki hedef, fren) her açılışta
bu kayıtlardan yeniden kurulur. Sandbox bundan sonra defterdeki pozisyona toparlanma emriyle getirilir (dugum.py).

Kurallar:
- Kol tanımı (config/paper.yaml satırı + boyut) kolun kimliğine bağlıdır. Tanım değişirse aynı adla açılamaz: yeni paper
  dönemi = yeni kol adı (kural 10: sonuca bakıp kural değiştirmek yeni denemedir).
- Karar, emirden ÖNCE yazılır (karar_ms): geriye dönük düzeltme yapılmadığının kanıtı. Aynı (kol, bar) için ikinci karar
  yazılmaz (yeniden başlatmada çift işlem olmaz).
"""
from __future__ import annotations

import dataclasses
import time
from datetime import UTC, datetime

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine

from tradebot.canli import dagitici as dg
from tradebot.canli.karar import Karar, KolDurum, izleyici_kur
from tradebot.canli.kollar import PaperKol
from tradebot.db import (
    paper_dagitim,
    paper_emir,
    paper_emir_olay,
    paper_karar,
    paper_kol,
    paper_kol_olay,
    paper_ozkaynak,
)


def tanim(kol: PaperKol) -> dict:
    return {"strateji": kol.strateji, "grup": kol.grup_adi, "grup_tanim": kol.grup, "zd": kol.zd,
            "parametre": kol.parametre, "ayar": {k: v for k, v in dataclasses.asdict(kol.ayar).items() if k != "olcut"},
            "sinif": kol.sinif, "baslangic_ozkaynak": kol.baslangic_ozkaynak}


def _liste(x) -> list:
    return [float(v) for v in x]


class PaperDefter:
    def __init__(self, motor: Engine, kod_surumu: str) -> None:
        self.motor, self.kod = motor, kod_surumu

    # ------------------------------------------------------------------ kol
    def kol_ac(self, kol: PaperKol, t_ms: int | None = None) -> bool:
        """Kolu açar; zaten açıksa tanımın aynı olduğunu doğrular. Döndürür: yeni açıldı mı."""
        t = tanim(kol)
        with self.motor.begin() as b:
            var = b.execute(select(paper_kol).where(paper_kol.c.kol == kol.ad)).one_or_none()
            if var is not None:
                if var.tanim != t:
                    raise ValueError(f"{kol.ad}: tanım değişti; yeni paper dönemi için yeni kol adı gerekir")
                return False
            b.execute(insert(paper_kol).values(kol=kol.ad, acilis=datetime.now(UTC),
                                               baslangic_ms=t_ms or int(time.time() * 1000),
                                               baslangic_ozkaynak=kol.baslangic_ozkaynak, sinif=kol.sinif, tanim=t,
                                               kod_surumu=self.kod))
            return True

    def durum(self, kol: PaperKol) -> KolDurum:
        """Kol durumunu defterden yeniden kurar."""
        with self.motor.connect() as b:
            dolumlar = list(b.execute(select(paper_emir_olay.c.enstruman, paper_emir_olay.c.miktar, paper_emir_olay.c.fiyat,
                                             paper_emir_olay.c.ucret).where(paper_emir_olay.c.kol == kol.ad,
                                                                            paper_emir_olay.c.tur == "dolum")))
            son = b.execute(select(paper_karar.c.ayrinti).where(paper_karar.c.kol == kol.ad)
                            .order_by(paper_karar.c.bar_ms.desc()).limit(1)).scalar()
            gecmis = [(int(t), float(o)) for t, o in b.execute(
                select(paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak).where(paper_ozkaynak.c.kol == kol.ad)
                .order_by(paper_ozkaynak.c.zaman_ms))]
        adet: dict[str, float] = {}
        nakit = kol.baslangic_ozkaynak
        for k, q, p, u in dolumlar:
            adet[k] = adet.get(k, 0.0) + q
            nakit -= q * p + u
        onceki = dict(zip(son["kimlikler"], son["etkin"], strict=True)) if son else {}
        kaldir = [(o.zaman_ms, o.ayrinti["onaylayan"], o.ayrinti["gerekce"]) for o in self.kol_olaylari(kol.ad, "acil_kaldir")]
        return KolDurum(ozkaynak=gecmis[-1][1] if gecmis else kol.baslangic_ozkaynak, nakit=nakit,
                        adet={k: a for k, a in adet.items() if abs(a) > 1e-12}, onceki_h=onceki, ilk=son is None,
                        izleyici=izleyici_kur(kol, gecmis, kaldir))

    # ------------------------------------------------------------------ karar, emir, olay
    def karar_var(self, kol: str, bar_ms: int) -> int | None:
        with self.motor.connect() as b:
            return b.execute(select(paper_karar.c.id).where(paper_karar.c.kol == kol, paper_karar.c.bar_ms == bar_ms)).scalar()

    def karar_yaz(self, k: Karar, veri_hash: str, gecikmeli: bool = False) -> int:
        """`gecikmeli`: açılışta, sınırdan sonra verilen karar (karar fiyatı ile gönderim arasındaki hareket yürütme
        maliyeti değildir; maliyet ölçümünde ayrılır)."""
        ayr = {"kimlikler": list(k.kimlikler), "hedef": _liste(k.hedef), "etkin": _liste(k.etkin_hedef),
               "kaymis": _liste(k.kaymis), "yeni": _liste(k.yeni), "islem": [bool(x) for x in k.islem],
               "fiyat": _liste(k.fiyat), "veto": list(k.veto), "miktar": k.miktar, "gecikmeli": gecikmeli}
        with self.motor.begin() as b:
            return int(b.execute(insert(paper_karar).values(
                kol=k.kol, bar_ms=k.bar_ms, karar_ms=int(time.time() * 1000), kod_surumu=self.kod,
                veri_hash=veri_hash[:64], durum=k.durum, ayrinti=ayr)).inserted_primary_key[0])

    def emir_yaz(self, kol: str, karar_id: int | None, istemci_emir_id: str, enstruman: str, istenen: float,
                 onaylanan: float, karar_fiyati: float, tur: str, risk: dict,
                 gonderim_fiyati: float | None = None) -> int:
        with self.motor.begin() as b:
            return int(b.execute(insert(paper_emir).values(
                kol=kol, karar_id=karar_id, istemci_emir_id=istemci_emir_id, enstruman=enstruman, istenen=istenen,
                onaylanan=onaylanan, karar_fiyati=karar_fiyati, gonderim_fiyati=gonderim_fiyati,
                zaman_ms=int(time.time() * 1000), tur=tur, risk=risk)).inserted_primary_key[0])

    def emir(self, istemci_emir_id: str):
        with self.motor.connect() as b:
            return b.execute(select(paper_emir).where(paper_emir.c.istemci_emir_id == istemci_emir_id)).one_or_none()

    def olay_yaz(self, emir_id: int, kol: str, tur: str, enstruman: str, miktar: float, fiyat: float | None,
                 ucret: float, zaman_ms: int, ayrinti: dict | None = None) -> int:
        with self.motor.begin() as b:
            return int(b.execute(insert(paper_emir_olay).values(
                emir_id=emir_id, kol=kol, tur=tur, enstruman=enstruman, miktar=miktar, fiyat=fiyat, ucret=ucret,
                zaman_ms=zaman_ms, ayrinti=ayrinti or {})).inserted_primary_key[0])

    def ozkaynak_yaz(self, kol: str, zaman_ms: int, d: KolDurum, fiyat: dict[str, float]) -> None:
        with self.motor.begin() as b:
            b.execute(insert(paper_ozkaynak).values(kol=kol, zaman_ms=zaman_ms, ozkaynak=d.ozkaynak, nakit=d.nakit,
                                                    pozisyon=d.adet, fiyat={k: fiyat[k] for k in d.adet if k in fiyat}))

    def dolum_sayisi(self, kol: str) -> int:
        with self.motor.connect() as b:
            return int(b.execute(select(func.count()).select_from(paper_emir_olay).where(
                paper_emir_olay.c.kol == kol, paper_emir_olay.c.tur == "dolum")).scalar())

    # ------------------------------------------------------------------ kol olayları
    def kol_olay_yaz(self, kol: str, tur: str, ayrinti: dict, zaman_ms: int | None = None) -> int:
        with self.motor.begin() as b:
            return int(b.execute(insert(paper_kol_olay).values(
                kol=kol, zaman_ms=zaman_ms or int(time.time() * 1000), tur=tur, kod_surumu=self.kod,
                ayrinti=ayrinti)).inserted_primary_key[0])

    def kol_olaylari(self, kol: str | None = None, tur: str | None = None, id_sonra: int = 0) -> list:
        q = select(paper_kol_olay).where(paper_kol_olay.c.id > id_sonra).order_by(paper_kol_olay.c.id)
        if kol is not None:
            q = q.where(paper_kol_olay.c.kol == kol)
        if tur is not None:
            q = q.where(paper_kol_olay.c.tur == tur)
        with self.motor.connect() as b:
            return list(b.execute(q))

    def sinif(self, kol: PaperKol, bit_ms: int | None = None) -> str:
        """Kolun sınıfı: son `terfi` olayı (bit_ms'den önce), yoksa tanımdaki. Sınıf tanımın parçası olduğu için terfi
        tanımı değiştirmez, olay olarak yazılır (kol yeniden açılmaz)."""
        son = [o for o in self.kol_olaylari(kol.ad, "terfi") if bit_ms is None or o.zaman_ms < bit_ms]
        return son[-1].ayrinti["yeni"] if son else kol.sinif

    # ------------------------------------------------------------------ dağıtıcı
    def ozkaynak_gecmisi(self, kol: str, bit_ms: int) -> list[tuple[int, float]]:
        """bit_ms'den önceki saatlik özkaynak işaretleri (zaman sıralı)."""
        with self.motor.connect() as b:
            return [(int(t), float(o)) for t, o in b.execute(
                select(paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak)
                .where(paper_ozkaynak.c.kol == kol, paper_ozkaynak.c.zaman_ms < bit_ms)
                .order_by(paper_ozkaynak.c.zaman_ms))]

    def kol_baslangic(self, kol: str) -> int | None:
        with self.motor.connect() as b:
            return b.execute(select(paper_kol.c.baslangic_ms).where(paper_kol.c.kol == kol)).scalar()

    def dagitim_oku(self, portfoy: str, hafta_ms: int) -> dict | None:
        with self.motor.connect() as b:
            return b.execute(select(paper_dagitim.c.ayrinti).where(
                paper_dagitim.c.portfoy == portfoy, paper_dagitim.c.hafta_ms == hafta_ms)).scalar()

    def dagitim_yaz(self, portfoy: str, hafta_ms: int, sonuc: dict) -> None:
        with self.motor.begin() as b:
            b.execute(insert(paper_dagitim).values(portfoy=portfoy, hafta_ms=hafta_ms, hesap_ms=int(time.time() * 1000),
                                                   kod_surumu=self.kod, kaldirac=float(sonuc["kaldirac"]),
                                                   ayrinti=sonuc))

    def dagitim_getir(self, portfoy: PaperKol, kaynaklar: list[PaperKol], hafta_ms: int) -> dict:
        """Haftanın dağıtımı: kayıtlıysa okunur (yeniden başlatmada aynı sonuç), yoksa hafta başına kadar kesilmiş
        defterle hesaplanıp yazılır."""
        var = self.dagitim_oku(portfoy.ad, hafta_ms)
        if var is not None:
            return var
        p = portfoy.parametre
        getiri, gun, sinif = {}, {}, {}
        for k in kaynaklar:
            getiri[k.ad] = dg.gunluk_getiri(self.ozkaynak_gecmisi(k.ad, hafta_ms), hafta_ms)
            bas = self.kol_baslangic(k.ad)
            gun[k.ad] = max(0.0, (hafta_ms - bas) / dg.GUN_MS) if bas is not None else 0.0
            sinif[k.ad] = self.sinif(k, hafta_ms)
        sonuc = dg.dagit(getiri, gun, sinif, p["onsel_sharpe"], dg.DagiticiAyar(**p["dagitici"]))
        sonuc["hafta_ms"] = hafta_ms
        self.dagitim_yaz(portfoy.ad, hafta_ms, sonuc)
        return sonuc
