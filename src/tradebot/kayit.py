"""Yapılandırılmış log: JSON satırları, UTC ISO zaman damgası, sır maskeleme.

Maskeleme iki katmanlı:
1. Adı sır çağrıştıran alanlar (key, secret, token, password, sifre, parola) her zaman `***` olur.
2. Tanımlı sırların düz değerleri, hangi alanda geçerse geçsin `***` ile değiştirilir (ör. bir hata mesajına
   gömülü URL'deki parola).
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

import structlog

from tradebot.ayar import Ayarlar

_SIR_AD = re.compile(r"(key|secret|token|password|passwd|sifre|parola|authorization)", re.I)
MASKE = "***"


def sir_maskeleyici(sirlar: list[str]):
    sirlar = sorted({s for s in sirlar if len(s) >= 4}, key=len, reverse=True)

    def _maskele(deger: Any) -> Any:
        if isinstance(deger, str):
            for s in sirlar:
                if s in deger:
                    deger = deger.replace(s, MASKE)
            return deger
        if isinstance(deger, dict):
            return {k: (MASKE if _SIR_AD.search(str(k)) else _maskele(v)) for k, v in deger.items()}
        if isinstance(deger, (list, tuple)):
            return type(deger)(_maskele(v) for v in deger)
        return deger

    def isleyici(_logger, _ad, olay: dict) -> dict:
        return {k: (MASKE if _SIR_AD.search(k) else _maskele(v)) for k, v in olay.items()}

    return isleyici


def kur(a: Ayarlar) -> None:
    """Uygulama başında bir kez çağrılır."""
    hedefler: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if a.log_dizini is not None:
        Path(a.log_dizini).mkdir(parents=True, exist_ok=True)
        hedefler.append(logging.FileHandler(Path(a.log_dizini) / "tradebot.jsonl", encoding="utf-8"))
    logging.basicConfig(format="%(message)s", level=a.log_seviyesi, handlers=hedefler, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="zaman"),
            structlog.processors.format_exc_info,
            sir_maskeleyici(a.sir_degerleri()),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(a.log_seviyesi)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def log(bilesen: str):
    return structlog.get_logger(bilesen=bilesen)
