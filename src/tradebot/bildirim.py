"""Bildirim: Telegram (Final Doküman §Operasyon). Token ya da sohbet tanımsızsa yalnız log.

Tek kullanıcı: bot yalnız `TRADEBOT_TELEGRAM_SOHBET`'e yazar. Metne sır girmez (log maskeleyicisinden geçer).
Aynı anahtar (ör. kontrol adı, olay adı) `sessiz_sn` içinde ikinci kez gönderilmez: alarm seli bildirimi öldürür.
Üç seviye: KRITIK her an anında gider; UYARI ve BILGI sessiz saatte (`sessiz_saat_utc`) biriktirilir, sessiz saat
bitince `bosalt()` tek mesajda gönderir (Final Doküman: "uyarılar gece sessiz saatte gruplanır").
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime

from tradebot.ayar import Ayarlar
from tradebot.kayit import log, metin_maskele

ISARET = {"KRITIK": "🔴", "UYARI": "🟠", "BILGI": "🟢"}
_SINIR = 4000   # Telegram mesaj sınırı 4096
_log = log("bildirim")


def sessiz_mi(saat: int, aralik: tuple[int, int]) -> bool:
    """`aralik` = (başlangıç, bitiş) UTC saat; gece yarısını aşabilir (19, 5)."""
    bas, bit = aralik
    return bas <= saat < bit if bas <= bit else (saat >= bas or saat < bit)


class Bildirici:
    def __init__(self, a: Ayarlar, sessiz_sn: float = 3600.0, gonderici=None,
                 saat: Callable[[], datetime] | None = None) -> None:
        self.a, self.sessiz_sn = a, sessiz_sn
        self._son: dict[str, float] = {}
        self._gonderici = gonderici or self._telegram
        self._saat = saat or (lambda: datetime.now(UTC))
        self.bekleyen: list[tuple[str, str]] = []   # sessiz saatte biriken (seviye, metin); yeniden başlatmada kaybolur
        sirlar = a.sir_degerleri()
        self._maskele = lambda m: metin_maskele(m, sirlar)   # metne gömülü sır (istisna metnindeki URL vb.) gitmesin

    @property
    def etkin(self) -> bool:
        return self.a.telegram_token is not None and bool(self.a.telegram_sohbet)

    def _sessiz(self) -> bool:
        return sessiz_mi(self._saat().hour, self.a.sessiz_saat_utc)

    def gonder(self, seviye: str, metin: str, anahtar: str | None = None) -> bool:
        """Döndürür: gönderildi mi. Susturulan, bekletilen ya da tanımsız kanal: False (yine loglanır)."""
        simdi = time.monotonic()
        if anahtar is not None and simdi - self._son.get(anahtar, -1e18) < self.sessiz_sn:
            return False
        metin = self._maskele(metin)
        bekle = self.etkin and seviye != "KRITIK" and self._sessiz()
        _log.warning("bildirim", seviye=seviye, metin=metin[:500],
                     kanal="bekliyor" if bekle else ("telegram" if self.etkin else "yok"))
        if bekle:
            self.bekleyen.append((seviye, metin))
            if anahtar is not None:
                self._son[anahtar] = simdi
            return False
        gitti = self.etkin and self._yolla(f"{ISARET.get(seviye, '')} TradeBot · {seviye}\n{metin}")
        # Susturma yalnız gerçekten gidenden sonra: gönderilemeyen KRİTİK alarm bir saat bastırılmasın (2026-10-18).
        if anahtar is not None and gitti:
            self._son[anahtar] = simdi
        return gitti

    def bosalt(self) -> int:
        """Sessiz saat bittiyse biriken bildirimleri gruplayıp gönderir. Döndürür: gönderilen bildirim sayısı."""
        if not self.bekleyen or self._sessiz():
            return 0
        bekleyen, self.bekleyen = self.bekleyen, []
        baslik = f"🌙 TradeBot · gece biriken {len(bekleyen)} bildirim"
        parcalar = [f"{ISARET.get(s, '')} {m}" for s, m in bekleyen]
        mesajlar, mesaj = [], baslik
        for p in parcalar:          # sınırı aşarsa birden çok mesaj
            if len(mesaj) + len(p) + 2 > _SINIR and mesaj != baslik:
                mesajlar.append(mesaj)
                mesaj = baslik + " (devam)"
            mesaj += "\n\n" + p
        mesajlar.append(mesaj)
        if not self._yolla(mesajlar[0]):   # kanal yoksa biriken uyarılar kaybolmasın: sonraki turda yeniden denenir
            self.bekleyen = bekleyen + self.bekleyen
            return 0
        for m in mesajlar[1:]:
            self._yolla(m)
        return len(bekleyen)

    def _yolla(self, metin: str) -> bool:
        try:
            self._gonderici(metin[:_SINIR])
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
