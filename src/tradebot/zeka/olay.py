"""Olaylar (veto/uyarı): zekâ katmanının motora ve backtest'e tek çıkışı. Yalnız eklenir (DB tetikleyicisi).

`gecerli_ms`: olayın görünür olduğu an. Canlıda yargının verildiği an; geçmişe dönük doldurmada yayın zamanı +
gecikme payı (aleyhte, varsayılan 60 sn). Backtest bar t'de yalnız `gecerli_ms ≤ t` olayları görür (point-in-time).

Veto kaldırma (`kaldir`): yanlış bir veto silinmez, `kaldir` olayı eklenir (`ayrinti.veto_id`); veto kaldırmanın
`gecerli_ms`'inde biter. Kaldırma riski artırır (kural 5/7): hiçbir otomatik yol çağırmaz, yalnız Scryne onayıyla CLI'dan
(`tradebot zeka veto-kaldir`) yazılır.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot.db import olay

GERIYE_DONUK_GECIKME_MS = 60_000


def yaz(motor: Engine, tur: str, enstruman: str, gecerli_ms: int, neden: str, rol: str, metin_id: int | None = None,
        yargi_id: int | None = None, bitis_ms: int | None = None, ayrinti: dict | None = None) -> int:
    with motor.begin() as b:
        return int(b.execute(insert(olay).values(
            zaman=datetime.now(UTC), tur=tur, enstruman=enstruman, gecerli_ms=gecerli_ms, bitis_ms=bitis_ms,
            neden=neden[:500], rol=rol, metin_id=metin_id, yargi_id=yargi_id, ayrinti=ayrinti or {})).inserted_primary_key[0])


def kaldir(motor: Engine, veto_id: int, gecerli_ms: int, neden: str, onay: str) -> int:
    """Veto `veto_id`'yi `gecerli_ms`'ten itibaren kaldırır (yeni kayıt). `onay`: kimin onayı (zorunlu)."""
    if not onay.strip():
        raise ValueError("veto kaldırma onay ister (kural 7)")
    with motor.connect() as b:
        v = b.execute(select(olay).where(olay.c.id == veto_id, olay.c.tur == "veto")).one_or_none()
    if v is None:
        raise ValueError(f"veto yok: {veto_id}")
    return yaz(motor, "kaldir", v.enstruman, gecerli_ms, neden, "manuel", v.metin_id, v.yargi_id, None,
               {"veto_id": veto_id, "onay": onay})


def _bitisler(b) -> dict[int, int]:
    """veto_id → en erken kaldırma anı."""
    out: dict[int, int] = {}
    for r in b.execute(select(olay.c.gecerli_ms, olay.c.ayrinti).where(olay.c.tur == "kaldir")):
        vid = int(r.ayrinti["veto_id"])
        out[vid] = min(out.get(vid, r.gecerli_ms), int(r.gecerli_ms))
    return out


def tum_vetolar(motor: Engine) -> list[tuple[str, int, int | None]]:
    """Backtest için bütün veto olayları: (enstrüman, gecerli_ms, bitis_ms); bitiş kaldırmayla öne çekilir.
    Maske `panel.veto_maskesi` ile kurulur."""
    with motor.connect() as b:
        kal = _bitisler(b)
        out = []
        for r in b.execute(select(olay.c.id, olay.c.enstruman, olay.c.gecerli_ms, olay.c.bitis_ms).where(olay.c.tur == "veto")):
            bitisler = [int(x) for x in (r.bitis_ms, kal.get(r.id)) if x is not None]
            out.append((r.enstruman, int(r.gecerli_ms), min(bitisler) if bitisler else None))
        return out


def aktif_vetolar(motor: Engine, t_ms: int) -> set[str]:
    """t anında geçerli veto listesi (risk motoru Portfoy.veto)."""
    return {k for k, bas, bit in tum_vetolar(motor) if bas <= t_ms and (bit is None or bit > t_ms)}
