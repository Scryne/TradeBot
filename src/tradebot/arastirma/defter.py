"""Deneme defteri (değişmez kural 10: deneme sayılır).

Akış: önce `plan_ac` (aile, hipotez, ızgara, piyasalar, geçme ölçütü) → her koşu `kaydet` ile plana bağlı girer.
Plansız koşu reddedilir. Kod sürümü (git) her kayıtta durur; commit edilmemiş ağaçla koşu "kirli" işaretlenir ve
`izin_kirli=True` verilmedikçe reddedilir (hangi sonucun hangi kodla alındığı her zaman bilinsin).
Aile başına tarama sayısı Deflated Sharpe'ın deneme sayısıdır.
"""
from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Engine

from tradebot.db import deneme, test_plani

KOK = Path(__file__).resolve().parents[3]


def kod_surumu() -> str:
    """git kısa hash (+ '-kirli' izlenen dosyalarda commit edilmemiş değişiklik varsa); git yoksa ortam değişkeni."""
    try:
        h = subprocess.run(["git", "-C", str(KOK), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                           timeout=10, check=True).stdout.strip()
        kirli = subprocess.run(["git", "-C", str(KOK), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return h + ("-kirli" if kirli else "")
    except (OSError, subprocess.SubprocessError):
        return os.environ.get("TRADEBOT_KOD_SURUMU", "bilinmiyor")


class Defter:
    def __init__(self, motor: Engine) -> None:
        self.motor = motor

    def plan_ac(self, kimlik: str, aile: str, hipotez: str, izgara: dict, piyasalar: list[str], olcut: str,
                izin_kirli: bool = False) -> str:
        surum = kod_surumu()
        if surum.endswith("-kirli") and not izin_kirli:
            raise RuntimeError(f"commit edilmemiş kodla test planı açılamaz ({surum}); önce commit")
        with self.motor.begin() as b:
            if b.execute(select(test_plani.c.kimlik).where(test_plani.c.kimlik == kimlik)).scalar():
                raise ValueError(f"plan zaten var: {kimlik} (planlar değiştirilmez; yeni plan aç)")
            b.execute(insert(test_plani).values(kimlik=kimlik, zaman=datetime.now(UTC), aile=aile, hipotez=hipotez,
                                                izgara=izgara, piyasalar=piyasalar, olcut=olcut, kod_surumu=surum,
                                                durum="acik"))
        return kimlik

    def plan_kapat(self, kimlik: str, sonuc: str) -> None:
        with self.motor.begin() as b:
            b.execute(update(test_plani).where(test_plani.c.kimlik == kimlik).values(durum="kapandi", sonuc=sonuc))

    def kaydet(self, plan: str, tur: str, strateji: str, aile: str, parametreler: dict, enstruman: str,
               zaman_dilimi: str, veri_hash: str, metrik: dict, sure_sn: float, izin_kirli: bool = False) -> int:
        surum = kod_surumu()
        if surum.endswith("-kirli") and not izin_kirli:
            raise RuntimeError(f"commit edilmemiş kodla deneme kaydedilemez ({surum})")
        with self.motor.begin() as b:
            durum = b.execute(select(test_plani.c.durum).where(test_plani.c.kimlik == plan)).scalar()
            if durum is None:
                raise ValueError(f"test planı yok: {plan} (önce plan_ac)")
            if durum != "acik":
                raise ValueError(f"test planı kapalı: {plan}")
            r = b.execute(insert(deneme).values(zaman=datetime.now(UTC), plan=plan, tur=tur, strateji=strateji, aile=aile,
                                                parametreler=parametreler, enstruman=enstruman, zaman_dilimi=zaman_dilimi,
                                                veri_hash=veri_hash, kod_surumu=surum, metrik=metrik, sure_sn=sure_sn))
            return int(r.inserted_primary_key[0])

    def deneme_sayisi(self, aile: str, tur: str = "tarama") -> int:
        with self.motor.connect() as b:
            return int(b.execute(select(func.count()).select_from(deneme).where(deneme.c.aile == aile, deneme.c.tur == tur))
                       .scalar() or 0)

    def aile_puanlari(self, aile: str, tur: str = "tarama") -> list[float]:
        """Ailenin tüm denemelerinin haftalık Sharpe'ları (DSR'da denemeler arası varyans için)."""
        with self.motor.connect() as b:
            return [float(m.get("sharpe", 0.0)) for m in b.execute(
                select(deneme.c.metrik).where(deneme.c.aile == aile, deneme.c.tur == tur)).scalars()]
