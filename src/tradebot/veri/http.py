"""Nazik HTTP istemcisi: kaynak başına asgari istek aralığı, 429/5xx ve bağlantı hatalarında üstel geri çekilme.

Spike 03: Dukascopy ~5 hızlı istekten sonra 503 verip IP'yi geçici engelliyor; GDELT 5 sn/istek; Binance arşivi rahat.
Tek, uzun ömürlü `httpx.Client` (bağlantı yeniden kullanımı).
"""
from __future__ import annotations

import threading
import time

import httpx

from tradebot.kayit import log

UA = "TradeBot/0.1 (kisisel arastirma; 218348029+Scryne@users.noreply.github.com)"


class YokHatasi(Exception):
    """Kaynakta dosya yok (404) — hata değil, bilgi."""


class NazikIstemci:
    def __init__(self, ad: str, aralik_sn: float = 0.0, deneme: int = 6, geri_cekilme_sn: float = 2.0,
                 zaman_asimi: float = 60.0, basliklar: dict | None = None) -> None:
        self.ad, self.aralik, self.deneme, self.geri = ad, aralik_sn, deneme, geri_cekilme_sn
        self._c = httpx.Client(timeout=zaman_asimi, follow_redirects=True, headers={"User-Agent": UA, **(basliklar or {})})
        self._kilit = threading.Lock()
        self._son = 0.0
        self._log = log(f"http.{ad}")

    def _bekle(self) -> None:
        with self._kilit:
            fark = self.aralik - (time.monotonic() - self._son)
            if fark > 0:
                time.sleep(fark)
            self._son = time.monotonic()

    def al(self, url: str, params: dict | None = None) -> bytes:
        return self._iste("GET", url, params=params)

    def gonder(self, url: str, json_govde: dict) -> bytes:
        """POST (JSON gövde); aynı aralık ve geri çekilme kuralları."""
        return self._iste("POST", url, json=json_govde)

    def _iste(self, yontem: str, url: str, **kw) -> bytes:
        son_hata: Exception | None = None
        for i in range(self.deneme):
            self._bekle()
            try:
                r = self._c.request(yontem, url, **kw)
                if r.status_code == 404:
                    raise YokHatasi(url)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
                r.raise_for_status()
                return r.content
            except YokHatasi:
                raise
            except (httpx.HTTPError, OSError) as e:
                son_hata = e
                bekle = self.geri * (2**i)
                self._log.warning("http_yeniden_dene", url=url, deneme=i + 1, hata=str(e)[:120], bekle_sn=bekle)
                time.sleep(bekle)
        raise RuntimeError(f"{self.ad}: {url} {self.deneme} denemede alınamadı: {son_hata}")

    def kapat(self) -> None:
        self._c.close()
