# ruff: noqa: E501  (soru tanımları Spike 04-A ile birebir; satır bölmek metni ve SORU_SHA'yı değiştirir)
"""Rol A1: Binance duyurusu → veto (Spike 04-A: 46/46 doğru, yanlış veto 0; anahtar kelime kuralı 21 yanlış veto).

Soru: bu duyuru `varlik`/USDT spot pozisyonu tutan birini nasıl etkiliyor? (Choice `etki` + Score `aciliyet`.)
Karar yalnız Choice'a dayanır (Spike 04 dersi 1); Score sıralama ve alarm önceliği içindir.

Karar kuralı: `zeka.karar.karar` (A2 ile ortak).
Soru tanımları Spike 04-A'nın birebir kopyasıdır; `SORU_SHA` testi değişikliği yakalar (değişiklik = yeni rol sürümü,
yeni ölçüm).
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.engine import Engine
from typesafe_sdk import Choice, Score

from tradebot.db import enstruman
from tradebot.zeka.karar import karar as ortak_karar

ROL = "A1_binance"
KAYNAK = "binance_duyuru"
ONEK = "A1"
VETO = {"token_delist", "usdt_pair_removed", "token_conversion"}

ETKI = Choice(
    instructions={
        "what": "Decide how this Binance announcement affects someone who holds `varlik` in a Binance SPOT account and "
                "trades it only against USDT (the `varlik`/USDT spot pair). Read `duyuru.baslik` and `duyuru.metin`. "
                "Judge only `varlik`, ignore other tokens in the text.",
        "not_for": "Do not predict price moves. Judge only what the announcement states.",
    },
    criteria={
        "token_delist": {
            "what": "Binance will delist `varlik` itself: all of its spot trading pairs stop and the token is removed from the exchange.",
            "not_for": "Removal of only some pairs of the token (e.g. /USDC, /BTC, /FDUSD, /TRY, /BNB) or only margin, loan, futures or Binance Alpha products."},
        "usdt_pair_removed": {
            "what": "The `varlik`/USDT spot pair specifically is removed or stops trading, while the token may stay listed through other pairs."},
        "token_conversion": {
            "what": "`varlik` is merged, swapped or converted into a different token or into fiat, so `varlik`/USDT trading ends and balances are converted.",
            "not_for": "A network or chain migration or upgrade where the token keeps its name and spot trading continues."},
        "other_pairs_or_products_removed": {
            "what": "Only other trading pairs of `varlik` (not /USDT) or other products (margin, loan, futures, collateral, Binance Alpha) are removed; `varlik`/USDT spot trading continues.",
            "examples": ["Notice of Removal of Spot Trading Pairs listing ENJ/USDC (for ENJ)", "Binance Margin will delist BTTC margin pairs (for BTTC)"]},
        "transfers_suspended": {
            "what": "Deposits and/or withdrawals of `varlik` on some or all networks are suspended, changed or discontinued because of an upgrade, hard fork, maintenance or network change, while spot trading is not impacted."},
        "positive_or_neutral": {
            "what": "A listing, new product, promotion, earn offer, trading competition, dividend, tick size change or other change with no negative effect on a `varlik`/USDT spot holder."},
        "not_about_asset": {"what": "The announcement does not concern `varlik` at all."},
    },
)

ACILIYET = Score(
    instructions="How urgently must a holder of a `varlik`/USDT spot position act because of this announcement?",
    criteria=[
        "No action: the announcement is irrelevant, neutral or positive for this holder.",
        "Informational: an operational change such as paused deposits or withdrawals, but spot trading and the position are unaffected.",
        "Attention: related pairs or products change; the holder should know but can keep trading the USDT pair.",
        "Act before a date: the holder's USDT spot position will stop trading or be converted at a scheduled date.",
        "Act immediately: trading ends imminently or funds are at risk (hack, insolvency, immediate halt).",
    ],
)

SORULAR = {"etki": ETKI, "aciliyet": ACILIYET}
AZAMI_ADAY = 40
_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{2,15}(?![A-Za-z0-9])")
# Tek harfli tabanlar (W, S, A, T…) düz metinde sıradan harflerle karışır: yalnız çift ya da parantez içinde aday olur
_TEK = re.compile(r"(?<![A-Za-z0-9])([A-Z])(?=\s*/\s*USDT|USDT(?![A-Za-z])|\))")
_CIFT = re.compile(r"(?<![A-Za-z0-9])([A-Z0-9]{1,15})\s*/?\s*USDT(?![A-Za-z])")
METIN_SINIRI = 4000


def adaylar(baslik: str, govde: str, bazlar: set[str]) -> list[str]:
    """Metinde büyük harfle geçen ve evrendeki bir USDT çiftinin tabanı olan semboller (tekil). `AZAMI_ADAY` kesmesi
    sıraya bağlı olduğundan önce metinde açıkça USDT çiftiyle geçenler gelir: toplu delist duyurusunda her duyuruda geçen
    BTC/ETH/BNB kotayı doldurup asıl hedefleri dışarıda bırakmasın (2026-10-18 denetimi)."""
    metin = f"{baslik}\n{govde}"
    ciftli = [t for t in _CIFT.findall(metin) if t in bazlar]
    duz = [t for t in _TOKEN.findall(metin) + _TEK.findall(metin) if t in bazlar]
    gorulen: list[str] = []
    for t in ciftli + duz:
        if t not in gorulen:
            gorulen.append(t)
    return gorulen[:AZAMI_ADAY]


def kesit(govde: str, varlik: str, sinir: int = METIN_SINIRI) -> str:
    """Modele giden metin. Uzun duyuruda varlık sınırdan sonra geçiyorsa geçtiği yerin çevresi de eklenir: aday tam
    metinden bulunuyor, model yalnız ilk 4000 karakteri görseydi "not_about_asset" deyip vetoyu kaçırırdı."""
    if len(govde) <= sinir:
        return govde
    bas = govde[: sinir - 1200]
    if re.search(rf"(?<![A-Za-z0-9]){re.escape(varlik)}(?![A-Za-z0-9])", bas):
        return govde[:sinir]
    m = re.search(rf"(?<![A-Za-z0-9]){re.escape(varlik)}(?![A-Za-z0-9])", govde)
    if m is None:
        return govde[:sinir]
    return bas + "\n…\n" + govde[max(0, m.start() - 500): m.start() + 600]


def state(baslik: str, govde: str, varlik: str) -> dict:
    return {"duyuru": {"baslik": baslik, "metin": kesit(govde, varlik)}, "varlik": varlik}


def karar(secim: str | None, guven: float, olasiliklar: dict, yukseltme: str | None, yukseltme_denendi: bool,
          esik: float = 0.5) -> tuple[bool, str]:
    return ortak_karar(secim, guven, olasiliklar, yukseltme, yukseltme_denendi, VETO, esik)


# --- servis arayüzü (A2 ile ortak) ---
def evren(motor: Engine) -> set[str]:
    with motor.connect() as b:
        return set(b.execute(select(enstruman.c.kimlik).where(enstruman.c.piyasa == "BINANCE",
                                                              enstruman.c.kimlik.like("%USDT"))).scalars())


def hedefler(m, evren_: set[str]) -> list[str]:
    bazlar = {k.removeprefix("BINANCE:").removesuffix("USDT") for k in evren_}
    return [f"BINANCE:{v}USDT" for v in adaylar(m.baslik, m.govde, bazlar)]


def hedef_state(m, kimlik: str) -> dict:
    return state(m.baslik, m.govde, kimlik.removeprefix("BINANCE:").removesuffix("USDT"))


def celiski(secim: str | None, m, kimlik: str) -> str | None:
    """Kodla denetlenebilen çelişki: `usdt_pair_removed` seçildi ama metinde `varlik/USDT` (ya da `varlikUSDT`) hiç
    geçmiyor. 2026-10-01: 15 yanlış vetonun 13'ü bu kalıptı (yalnız X/TUSD kaldırılmıştı; MEME'de güven 0,97). Çelişkili
    karar belirsiz sayılır → yükseltme modeline gider; yükseltme yoksa belirsizlik kuralı yine veto verir (riski azalt)."""
    if secim != "usdt_pair_removed":
        return None
    v = re.escape(kimlik.removeprefix("BINANCE:").removesuffix("USDT"))
    if re.search(rf"(?<![A-Za-z0-9]){v}\s*/\s*USDT(?![A-Za-z])|(?<![A-Za-z0-9]){v}USDT(?![A-Za-z])",
                 f"{m.baslik}\n{m.govde}"):
        return None
    return "metinde varlik/USDT yok"


def veto_suresi_ms(secim: str | None, ayar: dict) -> int | None:
    return None  # delist, USDT çifti kaldırma, dönüşüm: kalıcı


def bilgi_olayi(secim: str | None) -> str | None:
    return None
