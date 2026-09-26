"""Jev istemcisi: tek, uzun ömürlü TypeSafe istemcisi; her çağrı `jev_yargi`'ya dondurulur.

Kurallar (Spike 04, TypeSafe notu):
- Model sürümü sabittir (config/zeka.yaml). Sürüm API'den kalkarsa çağrı hata verir ve kayda geçer; sessizce başka
  sürüme düşülmez.
- Dondurma anahtarı (soru_sha, girdi_sha): aynı soru ve aynı girdi için kayıtlı cevap backtest'te okunur.
- Anahtar yalnız host'ta (kural 12); hiçbir log'a yazılmaz.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot.db import jev_yargi
from tradebot.kayit import log

_log = log("zeka.jev")


def kanonik_sha(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def soru_sha(sorular: dict) -> str:
    return kanonik_sha({k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v) for k, v in sorular.items()})


@dataclass(frozen=True)
class Yargi:
    id: int
    cevap: dict            # {soru: {"choice"/"score"/"noul", "confidence", "probabilities", …}}
    model: str | None
    hata: str | None = None

    def secim(self, soru: str) -> tuple[str | None, float, dict]:
        """(choice, confidence, probabilities) ya da hata varsa (None, 0, {})."""
        a = (self.cevap or {}).get(soru) or {}
        return a.get("choice"), float(a.get("confidence") or 0.0), a.get("probabilities") or {}


class JevIstemci:
    def __init__(self, motor: Engine, model: str, istemci=None, api_key: str | None = None) -> None:
        self.motor, self.model = motor, model
        if istemci is None:
            from typesafe_sdk import TypeSafeClient

            istemci = TypeSafeClient(api_key=api_key, model=model, timeout=30)
        self._c = istemci

    def sor(self, rol: str, hedef: str, state: dict, sorular: dict) -> Yargi:
        ssha, gsha = soru_sha(sorular), kanonik_sha(state)
        t0 = time.perf_counter()
        cevap, model, hata, token = None, None, None, None
        try:
            r = self._c.system_one(state, sorular, model=self.model)
            cevap = {k: a.model_dump(mode="json") for k, a in r.answers.items()}
            model, token = r.model, getattr(r.usage, "input_tokens", None)
        except Exception as e:  # noqa: BLE001 — hata kayda geçer; çağıran "riski azalt" yoluna gider
            hata = f"{type(e).__name__}: {e}"[:500]
            _log.warning("jev_hatasi", rol=rol, hedef=hedef, hata=hata)
        gecikme = (time.perf_counter() - t0) * 1000
        with self.motor.begin() as b:
            yid = b.execute(insert(jev_yargi).values(
                zaman=datetime.now(UTC), rol=rol, saglayici="jev", model_istenen=self.model, model_cozulen=model,
                soru_sha=ssha, girdi_sha=gsha, hedef=hedef[:256], cevap=cevap, gecikme_ms=gecikme, girdi_token=token,
                hata=hata)).inserted_primary_key[0]
        return Yargi(int(yid), cevap or {}, model, hata)


def donmus(motor: Engine, sorular: dict, state: dict, saglayici: str = "jev") -> dict | None:
    """Backtest için: bu soru + girdi için kayıtlı EN ESKİ başarılı cevap (canlı çağrı yok, kural 8)."""
    with motor.connect() as b:
        return b.execute(select(jev_yargi.c.cevap).where(
            jev_yargi.c.soru_sha == soru_sha(sorular), jev_yargi.c.girdi_sha == kanonik_sha(state),
            jev_yargi.c.saglayici == saglayici, jev_yargi.c.hata.is_(None)).order_by(jev_yargi.c.id)).scalar()
