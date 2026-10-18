"""Denetim izi: yalnız eklenen, hash zincirli kayıt. Her kayıt öncekinin hash'ini taşır.

`hash = sha256(onceki_hash + kanonik_json(zaman, bilesen, olay, veri))`. Aradaki bir kayıt sonradan
değiştirilir ya da silinirse `dogrula()` zincirin kırıldığı ilk kaydı döndürür. Eşzamanlı yazıcılar
PostgreSQL'de işlem düzeyinde danışma kilidiyle sıraya girer.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import Connection, Engine

from tradebot.db import denetim_izi

BASLANGIC = "0" * 64
_KILIT = 7_100_417  # denetim izi için sabit danışma kilidi anahtarı


def _kanonik(zaman: datetime, bilesen: str, olay: str, veri: Any) -> str:
    return json.dumps({"zaman": zaman.isoformat(), "bilesen": bilesen, "olay": olay, "veri": veri},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _hash(onceki: str, govde: str) -> str:
    return hashlib.sha256((onceki + govde).encode("utf-8")).hexdigest()


def _son_hash(baglanti: Connection) -> str:
    son = baglanti.execute(select(denetim_izi.c.hash).order_by(denetim_izi.c.id.desc()).limit(1)).scalar()
    return son or BASLANGIC


def kaydet(motor: Engine, bilesen: str, olay: str, veri: dict | None = None, zaman: datetime | None = None) -> str:
    """Kaydı ekler, yeni hash'i döndürür. `veri` JSON'a çevrilebilir olmalı; sır içermemeli."""
    zaman = (zaman or datetime.now(UTC)).astimezone(UTC)
    veri = veri or {}
    with motor.begin() as b:
        if b.dialect.name == "postgresql":
            b.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _KILIT})
        onceki = _son_hash(b)
        h = _hash(onceki, _kanonik(zaman, bilesen, olay, veri))
        b.execute(insert(denetim_izi).values(
            zaman=zaman, bilesen=bilesen, olay=olay, veri=veri, onceki_hash=onceki, hash=h))
    return h


def dogrula(motor: Engine) -> tuple[bool, int | None, int]:
    """Zinciri baştan sona doğrular. Dönüş: (sağlam mı, kırılan ilk kayıt id'si, kayıt sayısı)."""
    onceki = BASLANGIC
    with motor.connect() as b:
        n = b.execute(select(func.count()).select_from(denetim_izi)).scalar() or 0
        for r in b.execute(select(denetim_izi).order_by(denetim_izi.c.id)):
            # SQLite tz'yi düşürür; PostgreSQL oturum saat dilimi UTC değilse +03:00 gibi döner: kayıt UTC ile hash'lendi
            zaman = (r.zaman if r.zaman.tzinfo else r.zaman.replace(tzinfo=UTC)).astimezone(UTC)
            beklenen = _hash(onceki, _kanonik(zaman, r.bilesen, r.olay, r.veri))
            if r.onceki_hash != onceki or r.hash != beklenen:
                return False, r.id, n
            onceki = r.hash
    return True, None, n
