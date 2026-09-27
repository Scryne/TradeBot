"""Enstrüman kaydı: kimlik, sınıf, takvim, para birimi, kaynak ve tarihsel evren sınırları (ilk/son bar).

Kimlik "<PIYASA>:<SEMBOL>" biçimindedir (ör. BINANCE:BTCUSDT, DUKASCOPY:EURUSD, ARCA:SPY, BIST:THYAO). Kaynak sembolü
(Yahoo'da "THYAO.IS") `meta.kaynak_sembol`'de tutulur; kimlik kaynağa bağlı değildir.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml
from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from tradebot.db import enstruman as tablo

EVREN_YOLU = Path(__file__).resolve().parents[3] / "config" / "evren.yaml"


@dataclass(frozen=True)
class Enstruman:
    piyasa: str
    sembol: str
    sinif: str
    takvim: str
    para_birimi: str
    kaynak: str
    meta: dict = field(default_factory=dict)

    @property
    def kimlik(self) -> str:
        return f"{self.piyasa}:{self.sembol}"


def evren_yukle(yol: Path = EVREN_YOLU) -> dict:
    return yaml.safe_load(Path(yol).read_text(encoding="utf-8"))


def dukascopy_enstrumanlari(e: dict) -> list[Enstruman]:
    d = e["dukascopy"]
    out = []
    for sinif, tanim in d["semboller"].items():
        liste = tanim["liste"]
        ciftler = liste.items() if isinstance(liste, dict) else ((s, tanim["para"]) for s in liste)
        for sembol, para in ciftler:
            out.append(Enstruman(d["piyasa"], sembol, sinif, d["takvim"], para, "dukascopy", {"kaynak_sembol": sembol}))
    return out


def abd_etf_enstrumanlari(e: dict) -> list[Enstruman]:
    a = e["abd_etf"]
    return [Enstruman(a["piyasa"], s, a["sinif"], a["takvim"], a["para_birimi"], "yahoo", {"kaynak_sembol": s})
            for s in a["liste"]]


def bist_enstrumanlari(e: dict, hisseler: list[str]) -> list[Enstruman]:
    b = e["bist"]
    out = [Enstruman(b["piyasa"], s, "endeks", b["takvim"], b["para_birimi"], "yahoo", {"kaynak_sembol": f"{s}.IS"})
           for s in b["endeksler"]]
    out += [Enstruman(b["piyasa"], s, b["sinif"], b["takvim"], b["para_birimi"], "yahoo",
                      {"kaynak_sembol": f"{s}.IS", "evren_uyarisi": "bugünkü endeks bileşeni; geçmiş üyelik yok"})
            for s in hisseler]
    return out


def kripto_enstrumani(e: dict, sembol: str, meta: dict | None = None) -> Enstruman:
    k = e["kripto"]
    return Enstruman(k["piyasa"], sembol, k["sinif"], k["takvim"], k["para_birimi"], "binance", meta or {})


def mt5_enstrumanlari(e: dict, mevcut: dict[str, list[str]]) -> list[Enstruman]:
    """`mevcut`: hesap → köprünün bugün listelediği semboller (önekli gruplar buradan açılır; listede olmayan sabit
    sembol kayda girmez). Kaynak sembol = MT5 adı."""
    out = []
    for hesap, h in e["mt5"]["hesaplar"].items():
        adlar = mevcut.get(hesap, [])
        for sinif, g in h["gruplar"].items():
            semboller = [s for s in g.get("liste", []) if s in adlar]
            semboller += sorted(s for s in adlar if any(s.startswith(o) for o in g.get("on_ek", [])))
            for s in semboller:
                out.append(Enstruman(h["piyasa"], s, sinif, g["takvim"], g["para"], "mt5",
                                     {"kaynak_sembol": s, "hesap": hesap}))
    return out


def kaydet(motor: Engine, liste: list[Enstruman]) -> int:
    """Kayıtları ekler ya da günceller (ilk/son bar alanlarına dokunmaz)."""
    simdi = datetime.now(UTC)
    with motor.begin() as b:
        mevcut = set(b.execute(select(tablo.c.kimlik)).scalars())
        for e in liste:
            alanlar = {k: v for k, v in asdict(e).items()} | {"guncellendi": simdi}
            if e.kimlik in mevcut:
                b.execute(update(tablo).where(tablo.c.kimlik == e.kimlik).values(**alanlar))
            else:
                b.execute(tablo.insert().values(kimlik=e.kimlik, durum="aktif", **alanlar))
    return len(liste)


def sinir_guncelle(motor: Engine, kimlik: str, ilk_ms: int | None, son_ms: int | None, durum: str | None = None) -> None:
    deger: dict = {"guncellendi": datetime.now(UTC)}
    if ilk_ms is not None:
        deger["ilk_bar_ms"] = ilk_ms
    if son_ms is not None:
        deger["son_bar_ms"] = son_ms
    if durum is not None:
        deger["durum"] = durum
    with motor.begin() as b:
        b.execute(update(tablo).where(tablo.c.kimlik == kimlik).values(**deger))


def hepsi(motor: Engine, kaynak: str | None = None) -> list[dict]:
    q = select(tablo)
    if kaynak:
        q = q.where(tablo.c.kaynak == kaynak)
    with motor.connect() as b:
        return [dict(r._mapping) for r in b.execute(q.order_by(tablo.c.kimlik))]
