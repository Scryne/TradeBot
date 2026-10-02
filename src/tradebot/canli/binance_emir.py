"""Binance USDⓈ-M vadeli imzalı istemci (Faz 12, gerçek yürütme). Yalnız kilit düğümünün gerçek kolu kullanır.

Ortam: `demo` (https://demo-fapi.binance.com, Binance Demo Trading anahtarı) ya da `ana` (gerçek para). Uçlar ve
kurallar 2026-10-01'de resmî dokümandan doğrulandı (developers.binance.com/docs/derivatives/usds-margined-futures):
- Emir `POST /fapi/v1/order` MARKET, `newOrderRespType=RESULT` (dolum fiyatı ve adedi yanıtta), `newClientOrderId`
  `^[.A-Z:/a-z0-9_-]{1,36}$`. Aynı kimlik tekrar gelirse −4116: emir gitmiş demektir, sorgulanır (idempotent).
- `reduceOnly` yalnız tek yön pozisyon modunda geçerli: hedge modu açıksa düğüm çalışmaz.
- Hesap ve pozisyon v3 uçları; gelir `/fapi/v1/income` (en çok 1000 satır, son 3 ay).
- Ana ağda anahtar kısıtı `api.binance.com/sapi/v1/account/apiRestrictions`: çekim izni açıksa ya da IP kısıtı yoksa
  düğüm çalışmaz (kural 12). Demo'da bu uç yok.
Sırlar (`TRADEBOT_BINANCE_ANAHTAR`, `TRADEBOT_BINANCE_GIZLI`) yalnız host'ta; log'a ve deftere yazılmaz.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from urllib.parse import urlencode

import httpx

from tradebot.kayit import log

TABAN = {"demo": "https://demo-fapi.binance.com", "ana": "https://fapi.binance.com"}
SPOT_ANA = "https://api.binance.com"
KALDIRAC = 2                     # sembol başına marjin kaldıracı (maruziyeti boyut belirler; bu yalnız marjin tamponu)
ZARARSIZ = {-4046, -4059}        # marjin tipi / pozisyon modu zaten istenen gibi
_log = log("binance_emir")


class BorsaHatasi(RuntimeError):
    def __init__(self, kod: int, mesaj: str) -> None:
        super().__init__(f"{kod}: {mesaj}")
        self.kod, self.mesaj = kod, mesaj


def miktar_metni(x: float) -> str:
    """Float gürültüsü olmadan ondalık metin (0.30000000000000004 → "0.3")."""
    return f"{abs(x):.8f}".rstrip("0").rstrip(".")


def _ortalama(r: dict) -> float:
    """Ortalama dolum fiyatı: `avgPrice`, yoksa `cumQuote / executedQty`."""
    p = float(r.get("avgPrice") or 0)
    if p > 0:
        return p
    q = float(r.get("executedQty") or 0)
    return float(r.get("cumQuote") or 0) / q if q > 0 else 0.0


class VadeliIstemci:
    def __init__(self, ortam: str, anahtar: str, gizli: str, http: httpx.Client | None = None,
                 saat: Callable[[], float] = time.time, recv_window: int = 5000) -> None:
        if ortam not in TABAN:
            raise ValueError(f"ortam demo|ana olmalı: {ortam}")
        self.ortam, self.taban = ortam, TABAN[ortam]
        self._anahtar, self._gizli = anahtar, gizli.encode()
        self.http = http or httpx.Client(timeout=30)
        self.saat, self.recv = saat, recv_window
        self._hazir: set[str] = set()

    # ------------------------------------------------------------------ çekirdek
    def _imzali(self, yontem: str, yol: str, params: dict | None = None, taban: str | None = None):
        p = {k: v for k, v in (params or {}).items() if v is not None}
        p |= {"timestamp": int(self.saat() * 1000), "recvWindow": self.recv}
        q = urlencode(p)
        imza = hmac.new(self._gizli, q.encode(), hashlib.sha256).hexdigest()
        r = self.http.request(yontem, f"{taban or self.taban}{yol}?{q}&signature={imza}",
                              headers={"X-MBX-APIKEY": self._anahtar})
        try:
            d = r.json()
        except ValueError:
            d = {}
        if r.status_code >= 400 or (isinstance(d, dict) and int(d.get("code", 0) or 0) < 0):
            kod = int(d.get("code", -r.status_code)) if isinstance(d, dict) else -r.status_code
            raise BorsaHatasi(kod, str(d.get("msg", r.text[:200]) if isinstance(d, dict) else r.text[:200]))
        return d

    # ------------------------------------------------------------------ okuma
    def ozkaynak(self) -> float:
        """Marjin bakiyesi (cüzdan + gerçekleşmemiş kâr/zarar), USDT."""
        return float(self._imzali("GET", "/fapi/v3/account")["totalMarginBalance"])

    def pozisyonlar(self) -> dict[str, float]:
        return {x["symbol"]: float(x["positionAmt"]) for x in self._imzali("GET", "/fapi/v3/positionRisk")
                if abs(float(x["positionAmt"])) > 0}

    def gelir(self, bas_ms: int) -> list[dict]:
        """`bas_ms`'ten bu yana bütün gelir satırları (sayfalı). Tanınmayan türler de döner; çağıran seçer."""
        out, bas = [], int(bas_ms)
        while True:
            r = self._imzali("GET", "/fapi/v1/income", {"startTime": bas, "limit": 1000})
            out += [{"tur": x["incomeType"], "sembol": x.get("symbol") or "", "gelir": float(x["income"]),
                     "zaman_ms": int(x["time"]), "tranId": f"{x['incomeType']}:{x['tranId']}", "varlik": x.get("asset")}
                    for x in r]
            if len(r) < 1000:
                return out
            bas = int(r[-1]["time"]) + 1

    def emir_sorgu(self, sembol: str, istemci_id: str) -> dict:
        return self._imzali("GET", "/fapi/v1/order", {"symbol": sembol, "origClientOrderId": istemci_id})

    # ------------------------------------------------------------------ yazma
    def hazirla(self, sembol: str) -> None:
        """Sembolün ilk emrinden önce: çapraz marjin ve sabit marjin kaldıracı (zaten öyleyse zararsız hata)."""
        if sembol in self._hazir:
            return
        for yol, p in (("/fapi/v1/marginType", {"symbol": sembol, "marginType": "CROSSED"}),
                       ("/fapi/v1/leverage", {"symbol": sembol, "leverage": KALDIRAC})):
            try:
                self._imzali("POST", yol, p)
            except BorsaHatasi as e:
                if e.kod not in ZARARSIZ:
                    raise
        self._hazir.add(sembol)

    def emir(self, sembol: str, miktar: float, istemci_id: str, azaltan: bool) -> dict:
        """Piyasa emri. Döndürür: işaretli gerçekleşen adet, ortalama fiyat, durum, borsa emir no."""
        if not azaltan:
            self.hazirla(sembol)
        p = {"symbol": sembol, "side": "BUY" if miktar > 0 else "SELL", "type": "MARKET",
             "quantity": miktar_metni(miktar), "newClientOrderId": istemci_id, "newOrderRespType": "RESULT",
             "reduceOnly": "true" if azaltan else None}
        try:
            r = self._imzali("POST", "/fapi/v1/order", p)
        except BorsaHatasi as e:
            if e.kod != -4116:                       # aynı kimlik: emir daha önce gitmiş → sonucunu oku
                raise
            _log.warning("emir_tekrar_sorgulandi", sembol=sembol, istemci=istemci_id)
            r = self.emir_sorgu(sembol, istemci_id)
        adet = float(r.get("executedQty") or 0) * (1 if miktar > 0 else -1)
        fiyat = _ortalama(r)
        if abs(adet) > 0 and fiyat <= 0:   # Demo'da RESULT yanıtı dolu emirde avgPrice "0" döndü (2026-10-02): sorgula
            r = self.emir_sorgu(sembol, istemci_id)
            fiyat = _ortalama(r)
        if abs(adet) > 0 and fiyat <= 0:
            raise BorsaHatasi(-1, f"dolum fiyatı alınamadı: {sembol} {istemci_id}")
        return {"adet": adet, "fiyat": fiyat, "durum": r.get("status"), "emir_id": r.get("orderId")}

    # ------------------------------------------------------------------ güvenlik
    def dogrula(self) -> dict:
        """Düğüm açılırken: tek yön pozisyon modu; ana ağda çekim izni kapalı ve IP kısıtlı anahtar. Değilse hata."""
        if self._imzali("GET", "/fapi/v1/positionSide/dual").get("dualSidePosition"):
            raise RuntimeError("hesap hedge modunda: tek yön moduna alınmalı (reduceOnly yalnız tek yönde çalışır)")
        k = {}
        if self.ortam == "ana":
            k = self._imzali("GET", "/sapi/v1/account/apiRestrictions", taban=SPOT_ANA)
            if k.get("enableWithdrawals") or not k.get("ipRestrict"):
                raise RuntimeError("anahtarda çekim izni açık ya da IP kısıtı yok (kural 12): düğüm çalışmaz")
        return {"ortam": self.ortam, "ozkaynak": self.ozkaynak(), "kisit": {x: k.get(x) for x in
                                                                           ("enableWithdrawals", "ipRestrict")}}

    def hepsini_kapat(self) -> dict[str, dict]:
        """Bağımsız gözetmen için: bütün açık pozisyonları reduceOnly piyasa emriyle kapatır (riski azaltır)."""
        out = {}
        for s, q in sorted(self.pozisyonlar().items()):
            out[s] = self.emir(s, -q, f"GZ{int(self.saat()) // 60}-{s}"[:36], True)
        return out
