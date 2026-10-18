"""Yapılandırılmış log: JSON satırları, UTC ISO zaman damgası, sır maskeleme.

Maskeleme iki katmanlı:
1. Adı sır çağrıştıran alanlar (key, secret, token, password, sifre, parola) her zaman `***` olur.
2. Tanımlı sırların düz değerleri, hangi alanda geçerse geçsin `***` ile değiştirilir (ör. bir hata mesajına
   gömülü URL'deki parola).
"""
from __future__ import annotations

import itertools
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
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


def metin_maskele(metin: str, sirlar: list[str]) -> str:
    """Serbest metindeki sır değerlerini maskeler (Telegram, pano gibi log dışı kanallar için)."""
    for s in sorted({s for s in sirlar if s and len(s) >= 4}, key=len, reverse=True):
        metin = metin.replace(s, MASKE)
    return metin


def surec_adi(argv: list[str] | None = None) -> str:
    """Log dosyasının adı: komutun ilk iki alt komutu (`tradebot paper calis` → paper-calis)."""
    argv = sys.argv[1:] if argv is None else argv
    parca = list(itertools.takewhile(lambda x: not x.startswith("-"), argv))[:2]
    return re.sub(r"[^a-z0-9-]", "", "-".join(parca).lower()) or "tradebot"


def kur(a: Ayarlar) -> None:
    """Uygulama başında bir kez çağrılır. Dosya: süreç başına ayrı, 50 MB × 5 döner (2026-09-27 denetimi: bütün servisler
    tek dosyaya rotasyonsuz yazıyordu; çok süreçli rotasyon güvenli değildir, ayrı dosya bunu çözer)."""
    hedefler: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if a.log_dizini is not None:
        Path(a.log_dizini).mkdir(parents=True, exist_ok=True)
        hedefler.append(RotatingFileHandler(Path(a.log_dizini) / f"{surec_adi()}.jsonl", maxBytes=50_000_000,
                                            backupCount=5, encoding="utf-8"))
    logging.basicConfig(format="%(message)s", level=a.log_seviyesi, handlers=hedefler, force=True)
    # HTTP kütüphaneleri her isteği INFO'da basıyor (ilk yüklemede on binlerce satır); yalnız uyarı ve üstü.
    for gurultulu in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(gurultulu).setLevel(logging.WARNING)
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
