"""Bildirim: Telegram (Final Doküman §Operasyon; tam hali Faz 9). Token ya da sohbet tanımsızsa yalnız log.

Tek kullanıcı: bot yalnız `TRADEBOT_TELEGRAM_SOHBET`'e yazar. Metne sır girmez (log maskeleyicisinden geçer).
Aynı anahtar (ör. kontrol adı, olay adı) `sessiz_sn` içinde ikinci kez gönderilmez: alarm seli bildirimi öldürür.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from tradebot.ayar import Ayarlar
from tradebot.kayit import log

ISARET = {"KRITIK": "🔴", "UYARI": "🟠", "BILGI": "🟢"}
_log = log("bildirim")


class Bildirici:
    def __init__(self, a: Ayarlar, sessiz_sn: float = 3600.0, gonderici=None) -> None:
        self.a, self.sessiz_sn = a, sessiz_sn
        self._son: dict[str, float] = {}
        self._gonderici = gonderici or self._telegram

    @property
    def etkin(self) -> bool:
        return self.a.telegram_token is not None and bool(self.a.telegram_sohbet)

    def gonder(self, seviye: str, metin: str, anahtar: str | None = None) -> bool:
        """Döndürür: gönderildi mi. Susturulan ya da tanımsız kanal: False (yine loglanır)."""
        simdi = time.monotonic()
        if anahtar is not None:
            if simdi - self._son.get(anahtar, -1e18) < self.sessiz_sn:
                return False
            self._son[anahtar] = simdi
        _log.warning("bildirim", seviye=seviye, metin=metin[:500], kanal="telegram" if self.etkin else "yok")
        if not self.etkin:
            return False
        try:
            self._gonderici(f"{ISARET.get(seviye, '')} TradeBot · {seviye}\n{metin}"[:4000])
            return True
        except Exception as e:  # noqa: BLE001 — bildirim hatası bekçiyi durdurmaz
            _log.error("bildirim_gonderilemedi", hata=f"{type(e).__name__}: {e}"[:200])
            return False

    def _telegram(self, metin: str) -> None:
        url = f"https://api.telegram.org/bot{self.a.telegram_token.get_secret_value()}/sendMessage"
        govde = urllib.parse.urlencode({"chat_id": self.a.telegram_sohbet, "text": metin,
                                        "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=govde), timeout=10) as r:
            if not json.load(r).get("ok"):
                raise RuntimeError("telegram ok=false")
