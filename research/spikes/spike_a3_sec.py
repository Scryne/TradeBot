"""Spike A3 (2026-10-18): gerçek SEC 8-K'larında Jev `etki` sorusu. Beklenen etiket olaydan önce elle yazıldı.

Çalıştırma: `uv run python research/spikes/spike_a3_sec.py` (TYPESAFE_API_KEY ortamda; SEC ağına erişim).
Geçici SQLite; üretim defterine dokunmaz. Rapor: docs/spikes/09-a3-sec.md.
"""
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select

from tradebot.db import metadata, metin
from tradebot.metin import sec
from tradebot.veri.depo import HamDepo
from tradebot.zeka import a3_sec as a3
from tradebot.zeka.jev import JevIstemci

# (sembol, CIK, başvuru tarihi, beklenen etiket — yalnız rutin olmayan başvurular modele gider)
ORNEKLER = [
    ("ATVI", 718877, "2022-01-19", "being_acquired"),        # Microsoft birleşme anlaşması (1.01)
    ("ATVI", 718877, "2023-10-13", "being_acquired"),        # birleşme tamamlandı, delist (2.01, 3.01, 5.01)
    ("MSFT", 789019, "2022-01-18", "routine_or_positive"),   # tuzak 1: alan taraf
    ("SPLK", 1353283, "2023-09-21", "being_acquired"),       # Cisco anlaşması
    ("CSCO", 858877, "2023-09-21", "routine_or_positive"),   # tuzak 1
    ("XLNX", 743988, "2020-10-27", "being_acquired"),        # AMD anlaşması
    ("AMD", 2488, "2020-10-27", "routine_or_positive"),      # tuzak 1
    ("CELG", 816284, "2019-01-03", "being_acquired"),        # BMS anlaşması
    ("SIVB", 719739, "2023-03-17", "bankruptcy_or_delisting"),   # Chapter 11 (1.03)
    ("SMCI", 1375365, "2024-10-30", "accounting_problem"),   # E&Y istifası, endişe bildirimi (4.01)
    ("SMCI", 1375365, "2024-09-17", "bankruptcy_or_delisting"),  # Nasdaq uyum bildirimi (3.01, geç 10-K)
    ("INTC", 50863, "2024-08-01", "serious_negative"),       # %15 işten çıkarma, yeniden yapılanma (2.05)
    ("WBA", 1618921, "2025-03-06", "being_acquired"),        # Sycamore satın alımı
    ("MSFT", 789019, "2024-01-19", "serious_negative"),      # Midnight Blizzard (1.05)
    ("AAPL", 320193, "2023-05-10", "routine_or_positive"),   # tahvil ihracı (8.01/2.03 olası)
    # Kazanç bildirimleri (2.02): yanlış veto olmamalı (normal çeyrekler)
    ("AAPL", 320193, "2024-08-01", "routine_or_positive"),
    ("NVDA", 1045810, "2024-08-28", "routine_or_positive"),
    ("AMD", 2488, "2024-07-30", "routine_or_positive"),
    ("MSFT", 789019, "2024-07-30", "routine_or_positive"),
    ("COST", 909832, "2024-09-26", "routine_or_positive"),
    ("NFLX", 1065280, "2024-07-18", "routine_or_positive"),
    ("TSLA", 1318605, "2024-07-23", "routine_or_positive"),   # zayıf çeyrek ama rutin bildirim
]


def main() -> int:
    d = Path(tempfile.mkdtemp())
    m = create_engine(f"sqlite:///{d / 's.db'}")
    metadata.create_all(m)
    ham = HamDepo(d, m)
    s = sec.Sec8K(ham, m, uyeler=lambda: [])
    for sembol, cik, tarih, _ in ORNEKLER:
        sub = json.loads(s.http.al(sec.SUB_URL.format(cik=cik)))
        gun = int(datetime.fromisoformat(tarih).replace(tzinfo=UTC).timestamp() * 1000)
        yeni = [a for a in sec.yeni_8kler(sub, gun - 86_400_000) if a["tarih"] == tarih]
        if not yeni:
            print(f"{sembol} {tarih}: 8-K yok (recent listesinde değil)")
        s._kaydet(f"NASDAQ:{sembol}", cik, {**sub, "filings": {"recent": _filtre(sub, tarih)}}, gun - 86_400_000)
    jev = JevIstemci(m, "jev-1.13.0", api_key=os.environ["TYPESAFE_API_KEY"])
    beklenen = {(x[0], x[2]): x[3] for x in ORNEKLER}
    dogru = toplam = 0
    with m.connect() as b:
        satirlar = list(b.execute(select(metin).order_by(metin.c.yayin_ms)))
    for r in satirlar:
        sembol = r.meta["kodlar"][0]
        tarih = datetime.fromtimestamp(r.yayin_ms / 1000, UTC).strftime("%Y-%m-%d")
        tarih_b = next((t for (s_, t) in beklenen if s_ == sembol and abs(
            (datetime.fromisoformat(t) - datetime.fromisoformat(tarih)).days) <= 1), tarih)
        e = beklenen.get((sembol, tarih_b))
        if r.meta.get("atla"):
            print(f"ATLA  {sembol} {tarih} {r.meta['kalemler']} (beklenen {e})")
            if e is not None:
                toplam += 1
                dogru += e == "routine_or_positive"
            continue
        y = jev.sor(a3.ROL, f"spike:{r.dis_kimlik}", a3.hedef_state(r, f"NASDAQ:{sembol}"), a3.SORULAR)
        secim, guven, p = y.secim("etki")
        ok = secim == e
        toplam += e is not None
        dogru += bool(ok and e is not None)
        print(f"{'OK ' if ok else 'YANLIS' if e else '—  '} {sembol} {tarih} {r.meta['kalemler']} → {secim} ({guven:.2f})"
              f" beklenen {e}  {sorted(p.items(), key=lambda kv: -kv[1])[:2]}")
    print(f"\n{dogru}/{toplam} doğru")
    return 0


def _filtre(sub: dict, tarih: str) -> dict:
    r = sub["filings"]["recent"]
    i = [k for k, t in enumerate(r["filingDate"]) if t == tarih]
    return {k: [v[j] for j in i] for k, v in r.items() if isinstance(v, list)}


if __name__ == "__main__":
    sys.exit(main())
