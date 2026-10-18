"""Rol A3: SEC 8-K → Nasdaq hissesi için veto (yalnız riski azaltır: vetolu hissede yeni alış yok; kural 8).

Soru: bu 8-K, `sembol` hissesini tutan biri için ne anlama geliyor? (Choice `etki` + Score `aciliyet`.) İngilizce.
Karar yalnız Choice'a dayanır, kural A1/A2 ile aynı (`zeka.karar.karar`). Veto süreleri `config/zeka.yaml` `sec.veto_gun`.

Tuzaklar (soru tanımından önce yazıldı; Final Doküman: "rol eklerken önce tuzak listesi"):
1. Şirket başkasını SATIN ALIYOR (MSFT → ATVI, AMD → XLNX): hedef değil, `routine_or_positive`.
2. Şirket kendi borcunu ihraç ediyor ya da kredi anlaşması imzalıyor (1.01/2.03): rutin finansman.
3. Yönetici atama/ayrılığı, genel kurul, ana sözleşme değişikliği: rutin (zaten modele sorulmaz, `metin.sec.ROUTIN`).
4. Borsa uyum bildirimi (3.01) çoğu zaman "geç rapor" ya da "fiyat 1 $ altı" uyarısıdır, hemen delist değildir; yine
   de risk: `bankruptcy_or_delisting`.
5. Denetçi değişikliği: anlaşmazlıksız, rutin rotasyon `routine_or_positive`; istifa/endişe bildirimi `accounting_problem`.
6. Satın alma tamamlandı (2.01 + 3.01, hedef şirket): `being_acquired` (hisse nakde/başka hisseye dönüşür).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine
from typesafe_sdk import Choice, Score

from tradebot.db import enstruman

ROL = "A3_sec"
KAYNAK = "sec_8k"
ONEK = "A3"
VETO = {"bankruptcy_or_delisting", "being_acquired", "accounting_problem", "serious_negative"}

ETKI = Choice(
    instructions={
        "what": "Classify what this SEC Form 8-K filing means for a shareholder of `sembol` (the filing company, "
                "`sirket`). Read `bildirim.baslik` (the 8-K items) and `bildirim.metin`. Judge only from the company's "
                "own point of view as the filer.",
        "not_for": "Do not predict the stock price; only judge what the filing says.",
    },
    criteria={
        "bankruptcy_or_delisting": {
            "what": "The company files for bankruptcy or receivership, receives a notice of delisting or of failing a "
                    "continued listing rule from its exchange, announces it will delist, or discloses substantial doubt "
                    "about continuing as a going concern."},
        "being_acquired": {
            "what": "The company itself is the TARGET: it agreed to be acquired or merged into another company, a tender "
                    "offer is made for its shares, or its acquisition was completed and its shares are being converted "
                    "into cash or other securities.",
            "not_for": "The company acquiring another business, buying assets, or forming a partnership."},
        "accounting_problem": {
            "what": "Previously issued financial statements should no longer be relied upon or will be restated, the "
                    "auditor resigned or was dismissed together with disagreements or concerns, a material weakness, or "
                    "the company cannot file a periodic report on time.",
            "not_for": "A routine auditor rotation without disagreements; normal earnings results."},
        "serious_negative": {
            "what": "Other materially negative event for the company: default or acceleration of debt, large "
                    "impairment, material cybersecurity incident, major government or regulatory action against it, "
                    "loss or termination of a major contract or customer, or a large restructuring with plant closures.",
            "not_for": "Ordinary litigation updates, routine financing, or minor restructuring costs."},
        "routine_or_positive": {
            "what": "Routine or positive: earnings and operating results, debt issuance, credit agreements, share "
                    "buybacks, dividends, new contracts, the company acquiring other businesses, executive or board "
                    "changes, shareholder votes, investor presentations, other neutral information."},
    },
)

ACILIYET = Score(
    instructions="How urgently must a holder of `sembol` act because of this 8-K filing?",
    criteria=[
        "No action: routine or irrelevant information.",
        "Informational: worth noting, does not affect the position.",
        "Attention: an event that may change the risk of holding the shares.",
        "Act soon: the shares face a material negative or structural change (restatement, listing problem, sale of the company).",
        "Act immediately: bankruptcy, imminent delisting, or similar severe event.",
    ],
)

SORULAR = {"etki": ETKI, "aciliyet": ACILIYET}
AZAMI_ADAY = 5


def evren(motor: Engine) -> set[str]:
    with motor.connect() as b:
        return set(b.execute(select(enstruman.c.kimlik).where(enstruman.c.piyasa == "NASDAQ",
                                                              enstruman.c.sinif == "hisse")).scalars())


def hedefler(m, evren_: set[str]) -> list[str]:
    """Başvuranın sembolü (evrendeyse). Rutin kalemli başvuru (`atla`) hiç sorulmaz."""
    meta = m.meta or {}
    if meta.get("atla"):
        return []
    return [f"NASDAQ:{k}" for k in meta.get("kodlar", []) if f"NASDAQ:{k}" in evren_][:AZAMI_ADAY]


def hedef_state(m, kimlik: str) -> dict:
    meta = m.meta or {}
    return {"sembol": kimlik.removeprefix("NASDAQ:"), "sirket": meta.get("sirket"),
            "bildirim": {"baslik": m.baslik, "kalemler": meta.get("kalemler", []), "metin": m.govde[:8000]}}


def veto_suresi_ms(secim: str | None, ayar: dict) -> int | None:
    gun = ((ayar.get("sec") or {}).get("veto_gun") or {}).get(secim)
    return int(gun) * 86_400_000 if gun else None


def bilgi_olayi(secim: str | None) -> str | None:
    return None
