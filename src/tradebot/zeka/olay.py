"""Olaylar (veto/uyarı): zekâ katmanının motora ve backtest'e tek çıkışı. Yalnız eklenir (DB tetikleyicisi).

`gecerli_ms`: olayın görünür olduğu an. Canlıda yargının verildiği an; geçmişe dönük doldurmada yayın zamanı +
gecikme payı (aleyhte, varsayılan 60 sn). Backtest bar t'de yalnız `gecerli_ms ≤ t` olayları görür (point-in-time).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, insert, or_, select
from sqlalchemy.engine import Engine

from tradebot.db import olay

GERIYE_DONUK_GECIKME_MS = 60_000


def yaz(motor: Engine, tur: str, enstruman: str, gecerli_ms: int, neden: str, rol: str, metin_id: int | None = None,
        yargi_id: int | None = None, bitis_ms: int | None = None, ayrinti: dict | None = None) -> int:
    with motor.begin() as b:
        return int(b.execute(insert(olay).values(
            zaman=datetime.now(UTC), tur=tur, enstruman=enstruman, gecerli_ms=gecerli_ms, bitis_ms=bitis_ms,
            neden=neden[:500], rol=rol, metin_id=metin_id, yargi_id=yargi_id, ayrinti=ayrinti or {})).inserted_primary_key[0])


def aktif_vetolar(motor: Engine, t_ms: int) -> set[str]:
    """t anında geçerli veto listesi (risk motoru Portfoy.veto)."""
    with motor.connect() as b:
        return set(b.execute(select(olay.c.enstruman).where(
            olay.c.tur == "veto", olay.c.gecerli_ms <= t_ms,
            or_(olay.c.bitis_ms.is_(None), and_(olay.c.bitis_ms > t_ms)))).scalars())
