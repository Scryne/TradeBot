"""Paper kolları: `config/paper.yaml` → PaperKol listesi (Jev A/B çiftleri açılmış)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from tradebot.arastirma.turnuva import STRATEJILER, Ayar
from tradebot.cekirdek.boyut import kaldirac_dogrula

AYAR_YOLU = Path(__file__).resolve().parents[3] / "config" / "paper.yaml"
AGRESIF = "agresif"  # agresif gözlem kolu: kaynak kolların hedef ortalaması × tam Kelly, tavanlarla kırpılır


@dataclass(frozen=True)
class PaperKol:
    ad: str                 # defterdeki kimlik (Jev'li kopyada "+jev" eki)
    strateji: str
    grup_adi: str
    grup: dict              # dalga planındaki grup tanımı
    zd: str
    ayar: Ayar              # boyut + frenler (turnuva.Ayar; jev_veto bu kopyanın veto kullanıp kullanmadığı)
    parametre: dict         # *_gun parametreleri (turnuva.cevir ile bara çevrilir)
    sinif: str              # B | A
    baslangic_ozkaynak: float

    @property
    def yon(self) -> str:
        return self.grup.get("yon", "long")

    @property
    def jev(self) -> bool:
        return self.ayar.jev_veto


def oku(yol: Path = AYAR_YOLU) -> dict:
    return yaml.safe_load(Path(yol).read_text(encoding="utf-8"))


def kollar(d: dict | None = None) -> list[PaperKol]:
    d = d or oku()
    out = []
    for k in d["kollar"]:
        if k["strateji"] not in STRATEJILER or k["strateji"] == AGRESIF:
            raise ValueError(f"bilinmeyen strateji: {k['strateji']}")
        b = d["boyutlar"][k["boyut"]]
        kaldirac_dogrula(b["kaldirac"])
        for jev in ([False, True] if d.get("jev_ab", True) else [False]):
            ayar = Ayar(hedef_vol=b["hedef_vol"], kaldirac=b["kaldirac"], vol_pencere_gun=b["vol_pencere_gun"],
                        frenler=bool(d.get("frenler", True)), bant=b["bant"], jev_veto=jev)
            out.append(PaperKol(k["ad"] + ("+jev" if jev else ""), k["strateji"], k["grup"], d["gruplar"][k["grup"]],
                                k["zd"], ayar, dict(k["parametre"]), k.get("sinif", "B"),
                                float(d.get("baslangic_ozkaynak", 100_000))))
    ag = d.get("agresif")
    if ag:
        b = d["boyutlar"][ag["boyut"]]
        ayar = Ayar(hedef_vol=b["hedef_vol"], kaldirac=b["kaldirac"], vol_pencere_gun=b["vol_pencere_gun"],
                    frenler=bool(d.get("frenler", True)), bant=b["bant"], jev_veto=False)
        bilinen = {k.ad for k in out}
        eksik = [x for x in ag["kaynaklar"] if x not in bilinen]
        if eksik:
            raise ValueError(f"agresif kolun kaynakları yok: {eksik}")
        out.append(PaperKol(ag["ad"], AGRESIF, ag["grup"], d["gruplar"][ag["grup"]], "1h", ayar,
                            {"kaynaklar": list(ag["kaynaklar"]), "kelly_carpani": float(ag["kelly_carpani"])}, "gozlem",
                            float(d.get("baslangic_ozkaynak", 100_000))))
    adlar = [k.ad for k in out]
    if len(set(adlar)) != len(adlar):
        raise ValueError("kol adları tekil olmalı")
    return out
