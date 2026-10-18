"""Alpaca PAPER istemcisi (Nasdaq kolu; REST, httpx). Yalnız `paper-api.alpaca.markets`: canlı (gerçek para) uç
noktası kodda yoktur. Gerçek paraya geçiş ayrı karar ve Scryne'ın açık onayıdır (kural 7); o gün bu dosyaya değil,
ayrı ve onaylı bir yürütme katmanına eklenir.

Kimlik: `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY` başlıkları; anahtar yalnız host `.env`'inde (kural 12), log'a girmez
(maskeleyici `ayar.SIR_ALANLARI`).

Emir: piyasa emri, `time_in_force` = `opg` (açılış müzayedesi; 19:00–09:28 ET arası kabul) ya da `day`. Kesirli
adet yalnız `day` piyasa emrinde olur; düğüm tam adet gönderir. `client_order_id` defterdeki emir kimliğidir (çift emir
koruması: aynı kimlik ikinci kez kabul edilmez).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

from tradebot.kayit import log

PAPER_URL = "https://paper-api.alpaca.markets"
VERI_URL = "https://data.alpaca.markets"
_log = log("canli.alpaca")


class AlpacaHatasi(RuntimeError):
    def __init__(self, durum: int, metin: str) -> None:
        super().__init__(f"alpaca {durum}: {metin[:300]}")
        self.durum = durum


@dataclass(frozen=True)
class Dolum:
    istemci_id: str
    emir_id: str
    durum: str                  # new | accepted | filled | partially_filled | canceled | rejected | expired …
    adet: float                 # işaretli dolan adet (alış +)
    fiyat: float | None         # ortalama dolum fiyatı


class AlpacaPaper:
    def __init__(self, anahtar: str, gizli: str, zaman_asimi: float = 20.0, deneme: int = 3,
                 istemci: httpx.Client | None = None) -> None:
        if not anahtar or not gizli:
            raise ValueError("Alpaca paper anahtarı tanımsız")
        self._c = istemci or httpx.Client(timeout=zaman_asimi, headers={
            "APCA-API-KEY-ID": anahtar, "APCA-API-SECRET-KEY": gizli, "Accept": "application/json"})
        self.deneme = deneme

    def _iste(self, yontem: str, yol: str, kok: str = PAPER_URL, **kw):
        son: Exception | None = None
        for i in range(self.deneme):
            try:
                r = self._c.request(yontem, kok + yol, **kw)
            except httpx.HTTPError as e:      # ağ hatası: yeniden dene (emir gönderimi çağıran tarafta korunur)
                son = e
                time.sleep(2 ** i)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                son = AlpacaHatasi(r.status_code, r.text)
                time.sleep(2 ** i)
                continue
            if r.status_code >= 400:
                raise AlpacaHatasi(r.status_code, r.text)
            return r.json() if r.content else None
        raise son if isinstance(son, AlpacaHatasi) else AlpacaHatasi(0, f"ağ: {son}")

    # ------------------------------------------------------------------ hesap
    def hesap(self) -> dict:
        return self._iste("GET", "/v2/account")

    def saat(self) -> dict:
        return self._iste("GET", "/v2/clock")

    def pozisyonlar(self) -> dict[str, float]:
        """sembol → işaretli adet."""
        # qty kısa pozisyonda eksi de gelebilir: işaret `side`'dan alınır
        return {p["symbol"]: abs(float(p["qty"])) * (1.0 if p.get("side", "long") == "long" else -1.0)
                for p in self._iste("GET", "/v2/positions") or []}

    # ------------------------------------------------------------------ emir
    def emir_gonder(self, sembol: str, adet: float, istemci_id: str, zaman: str = "opg") -> dict:
        """Piyasa emri. `adet` işaretli (+ alış). Aynı `istemci_id` tekrar gönderilirse Alpaca reddeder (422)."""
        if adet == 0:
            raise ValueError("sıfır adet")
        govde = {"symbol": sembol, "qty": f"{abs(adet):g}", "side": "buy" if adet > 0 else "sell", "type": "market",
                 "time_in_force": zaman, "client_order_id": istemci_id[:128]}
        return self._iste("POST", "/v2/orders", content=json.dumps(govde), headers={"Content-Type": "application/json"})

    def emir(self, istemci_id: str) -> Dolum | None:
        """İstemci kimliğiyle emir durumu (yoksa None)."""
        try:
            o = self._iste("GET", "/v2/orders:by_client_order_id", params={"client_order_id": istemci_id})
        except AlpacaHatasi as e:
            if e.durum == 404:
                return None
            raise
        isaret = 1.0 if o.get("side") == "buy" else -1.0
        dolan = float(o.get("filled_qty") or 0.0)
        fiyat = float(o["filled_avg_price"]) if o.get("filled_avg_price") else None
        return Dolum(istemci_id, o["id"], o["status"], isaret * dolan, fiyat)

    def emir_iptal(self, emir_id: str) -> None:
        self._iste("DELETE", f"/v2/orders/{emir_id}")

    def kapat(self, sembol: str) -> dict | None:
        """Tek sembolün pozisyonunu piyasa emriyle kapatır (gözetmen; yalnız düğümün kendi sembolleri). Yoksa None."""
        try:
            return self._iste("DELETE", f"/v2/positions/{sembol}")
        except AlpacaHatasi as e:
            if e.durum == 404:
                return None
            raise

    def hepsini_kapat(self) -> list[dict]:
        """Bütün açık emirleri iptal eder, bütün pozisyonları piyasa emriyle kapatır (gözetmen; riski azaltan)."""
        return self._iste("DELETE", "/v2/positions", params={"cancel_orders": "true"}) or []

    # ------------------------------------------------------------------ veri (ücretsiz IEX)
    def son_fiyatlar(self, semboller: list[str]) -> dict[str, float]:
        if not semboller:
            return {}
        d = self._iste("GET", "/v2/stocks/trades/latest", kok=VERI_URL,
                       params={"symbols": ",".join(semboller), "feed": "iex"})
        return {s: float(t["p"]) for s, t in (d.get("trades") or {}).items()}
