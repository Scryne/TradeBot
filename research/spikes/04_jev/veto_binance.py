"""Spike 04-A: Jev ile Binance duyuru vetosu (rol A1). Gerçek duyurular, elle etiket, anahtar kelime kıyası.

Soru: bu duyuru, `varlik`/USDT spot pozisyonu tutan birini nasıl etkiliyor? Kod kuralı: etki ∈ VETO ise o varlıkta
yeni alım durur ve pozisyon küçültülür. Etiketler Claude'un metinleri okuyarak verdiği altın cevaplardır
(Scryne gözden geçirebilir); tartışmalı durumlarda kabul kümesi birden fazla seçenek içerir.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

from typesafe_sdk import Choice, Score, TypeSafeClient

MODEL = "jev-1.13.0"
VETO = {"token_delist", "usdt_pair_removed", "token_conversion"}
D = Path(__file__).parent / "data"

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

# (duyuru indeksi, varlık, altın etiket, kabul edilen etiketler)
ETIKET = [
    (1, "SSV", "other_pairs_or_products_removed"), (1, "MANTA", "other_pairs_or_products_removed"),
    (2, "ENJ", "other_pairs_or_products_removed"), (2, "AIXBT", "other_pairs_or_products_removed"),
    (2, "TNSR", "other_pairs_or_products_removed"), (3, "QNT", "other_pairs_or_products_removed"),
    (3, "COOKIE", "other_pairs_or_products_removed"), (4, "VANA", "other_pairs_or_products_removed"),
    (5, "USDP", "token_delist"), (6, "API3", "other_pairs_or_products_removed"),
    (7, "SAGA", "other_pairs_or_products_removed"), (8, "BDXN", "other_pairs_or_products_removed"),
    (10, "ICX", "token_delist"), (10, "STORJ", "token_delist"), (10, "SCRT", "token_delist"),
    (11, "LTC", "other_pairs_or_products_removed"), (11, "SUI", "other_pairs_or_products_removed"),
    (13, "APT", "other_pairs_or_products_removed"), (14, "BTTC", "other_pairs_or_products_removed"),
    (15, "SKL", "other_pairs_or_products_removed"), (16, "ACX", "token_delist"), (16, "VIC", "token_delist"),
    (16, "PYR", "token_delist"), (17, "AEUR", "token_delist", {"token_delist", "token_conversion"}),
    (18, "MOVE", "other_pairs_or_products_removed"), (18, "POL", "other_pairs_or_products_removed"),
    (21, "INJ", "transfers_suspended"), (22, "ZIL", "transfers_suspended"), (23, "LUNA", "transfers_suspended"),
    (25, "STG", "token_conversion", {"token_conversion", "usdt_pair_removed", "token_delist"}),
    (25, "ZRO", "positive_or_neutral", {"positive_or_neutral", "not_about_asset"}),
    (28, "VANA", "transfers_suspended"), (32, "VET", "transfers_suspended"), (34, "AVA", "transfers_suspended"),
    (36, "BB", "transfers_suspended"), (39, "CFX", "transfers_suspended"),
    (40, "HYPE", "positive_or_neutral"), (45, "COAI", "positive_or_neutral"), (46, "PLUME", "positive_or_neutral"),
    (49, "APT", "positive_or_neutral"), (53, "PROVE", "positive_or_neutral"),
    # kontrol: metinde geçmeyen varlık
    (10, "ETH", "not_about_asset"), (21, "BTC", "not_about_asset"), (2, "DOGE", "not_about_asset"),
    (40, "XRP", "not_about_asset"), (25, "SOL", "not_about_asset", {"not_about_asset", "positive_or_neutral"}),
]


def anahtar_kelime(duyuru: dict, varlik: str) -> bool:
    """Naif kıyas: metinde 'delist' ya da 'removal' geçiyor ve varlık adı geçiyorsa veto."""
    m = (duyuru["baslik"] + " " + duyuru["govde"]).lower()
    return ("delist" in m or "removal" in m or "remove" in m) and varlik.lower() in m


def main() -> None:
    sec = json.load(open(D / "binance_secki.json", encoding="utf-8"))
    istemci = TypeSafeClient()
    kayit, sureler = [], []
    soru_hash = hashlib.sha256(json.dumps([ETKI.model_dump(), ACILIYET.model_dump()], sort_keys=True, default=str).encode()).hexdigest()[:16]
    for e in ETIKET:
        i, varlik, altin = e[:3]
        kabul = e[3] if len(e) > 3 else {altin}
        d = sec[i]
        state = {"duyuru": {"baslik": d["baslik"], "metin": d["govde"][:4000]}, "varlik": varlik}
        t0 = time.perf_counter()
        r = istemci.system_one(state, {"etki": ETKI, "aciliyet": ACILIYET}, model=MODEL)
        sureler.append(time.perf_counter() - t0)
        c, s = r.choices["etki"], r.scores["aciliyet"]
        kayit.append({
            "i": i, "varlik": varlik, "baslik": d["baslik"][:80], "altin": altin, "kabul": sorted(kabul),
            "jev": c.choice, "guven": round(c.confidence, 3), "p": {k: round(v, 3) for k, v in c.probabilities.items()},
            "aciliyet": round(s.score, 2), "aciliyet_guven": round(s.confidence, 3),
            "dogru": c.choice in kabul, "veto_altin": altin in VETO, "veto_jev": c.choice in VETO,
            "veto_kelime": anahtar_kelime(d, varlik), "model": r.model, "girdi_token": r.usage.input_tokens,
        })
        k = kayit[-1]
        print(f"{'✓' if k['dogru'] else '✗'} {varlik:<6} altın={altin:<32} jev={c.choice:<32} güven={c.confidence:.2f} aciliyet={s.score:.2f}")

    json.dump({"model": MODEL, "soru_hash": soru_hash, "kayit": kayit}, open(D / "veto_binance_sonuc.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n = len(kayit)
    dogru = sum(k["dogru"] for k in kayit)
    print(f"\nETKİ doğruluğu: {dogru}/{n} = %{dogru / n * 100:.0f}")
    for ad, anahtar in (("Jev", "veto_jev"), ("Anahtar kelime", "veto_kelime")):
        tp = sum(k[anahtar] and k["veto_altin"] for k in kayit)
        fp = sum(k[anahtar] and not k["veto_altin"] for k in kayit)
        fn = sum((not k[anahtar]) and k["veto_altin"] for k in kayit)
        print(f"{ad:<15} VETO — doğru veto {tp}, yanlış alarm {fp}, KAÇIRILAN {fn}  (gerçek veto sayısı {tp + fn})")
    for esik in (0.0, 0.5, 0.7, 0.9):
        alt = [k for k in kayit if k["guven"] >= esik]
        if alt:
            print(f"güven ≥ {esik}: {len(alt)}/{n} örnek, doğruluk %{sum(k['dogru'] for k in alt) / len(alt) * 100:.0f}")
    yanlis = [k for k in kayit if not k["dogru"]]
    print("\nYanlışlar:")
    for k in yanlis:
        print(f"  #{k['i']} {k['varlik']}: altın {k['altin']} ← jev {k['jev']} (güven {k['guven']}) | {k['baslik']}")
    print(f"\nmodel {kayit[0]['model']} · gecikme medyan {statistics.median(sureler):.2f} sn (ilk {sureler[0]:.1f} sn) · "
          f"ortalama girdi {statistics.mean(k['girdi_token'] or 0 for k in kayit):.0f} token")


if __name__ == "__main__":
    main()
