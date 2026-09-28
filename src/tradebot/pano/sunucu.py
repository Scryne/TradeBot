"""Pano HTTP sunucusu (FastAPI). Yalnız GET: `/api/pano`, `/api/kol/{kol}`, `/api/saglik`; derlenmiş arayüz `/`'de.

Güvenlik: compose portu yalnız 127.0.0.1'e açar; dışarıya Tailscale (`tailscale serve`) taşır. Uygulama yazma yolu
sunmaz (yalnız GET; başka yöntem 405). Yanıtlara sır girmez: sağlık yalnız "tanımlı/tanımsız" bildirir.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from tradebot.ayar import Ayarlar
from tradebot.pano import veri

SAGLIK_TTL_SN = 60.0


class SaglikOnbellek:
    """Sağlık kontrolleri (DNS, NTP, MT5 köprüsü) saniyeler sürer: arka planda en çok dakikada bir yenilenir, istek
    beklemez. İlk istekte sonuç yoksa `hazir: false` döner."""

    def __init__(self, a: Ayarlar, ttl_sn: float = SAGLIK_TTL_SN, kontrol=None) -> None:
        from tradebot import saglik

        self.a, self.ttl = a, ttl_sn
        self.kontrol = kontrol or saglik.hepsi
        self.sonuc: dict | None = None
        self.zaman = 0.0
        self._kilit = threading.Lock()
        self._calisiyor = False

    def _yenile(self) -> None:
        try:
            sonuclar = [asdict(s) for s in self.kontrol(self.a)]
            for s in sonuclar:
                s.pop("olcum", None)   # ham ölçüm (sır listesi dahil) panoya gitmez
            self.sonuc = {"hazir": True, "zaman_ms": int(time.time() * 1000), "kontroller": sonuclar}
        except Exception as e:  # noqa: BLE001
            self.sonuc = {"hazir": True, "zaman_ms": int(time.time() * 1000),
                          "kontroller": [{"ad": "saglik", "durum": "HATA", "ayrinti": f"{type(e).__name__}: {e}"[:200]}]}
        finally:
            self.zaman = time.monotonic()
            with self._kilit:
                self._calisiyor = False

    def al(self) -> dict:
        with self._kilit:
            eski = self.sonuc is None or time.monotonic() - self.zaman > self.ttl
            if eski and not self._calisiyor:
                self._calisiyor = True
                threading.Thread(target=self._yenile, daemon=True).start()
        return self.sonuc or {"hazir": False, "kontroller": []}


def uygulama(motor: Engine, a: Ayarlar, arayuz: Path | None = None, saat=lambda: int(time.time() * 1000),
             saglik_onbellek: SaglikOnbellek | None = None) -> FastAPI:
    from tradebot.arastirma.defter import kod_surumu

    app = FastAPI(title="TradeBot pano", docs_url=None, redoc_url=None, openapi_url=None)
    saglik_ = saglik_onbellek or SaglikOnbellek(a)
    surum = kod_surumu()

    @app.middleware("http")
    async def _basliklar(istek, sonraki):
        if istek.method not in ("GET", "HEAD"):
            return JSONResponse({"hata": "pano salt okunur"}, status_code=405)
        yanit = await sonraki(istek)
        yanit.headers["X-Content-Type-Options"] = "nosniff"
        yanit.headers["Referrer-Policy"] = "no-referrer"
        yanit.headers["X-Frame-Options"] = "DENY"
        yanit.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if istek.url.path.startswith("/api/"):
            yanit.headers["Cache-Control"] = "no-store"
        return yanit

    @app.get("/api/pano")
    def _pano():
        return veri.pano(motor, saat(), a.veri_dizini, surum)

    @app.get("/api/kol/{ad:path}")
    def _kol(ad: str):
        r = veri.kol(motor, ad, saat())
        if r is None:
            raise HTTPException(404, f"kol yok: {ad}")
        return r

    @app.get("/api/saglik")
    def _saglik():
        return saglik_.al()

    if arayuz is not None and (arayuz / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=arayuz / "assets"), name="assets")

        @app.get("/{yol:path}")
        def _arayuz(yol: str):
            dosya = (arayuz / yol).resolve()
            if yol and dosya.is_file() and arayuz.resolve() in dosya.parents:
                return FileResponse(dosya)
            return FileResponse(arayuz / "index.html", headers={"Cache-Control": "no-cache"})

    return app
