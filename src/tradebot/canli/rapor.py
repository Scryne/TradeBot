"""Haftalık paper raporu (Faz 7): tamamen defterden türetilir, her zaman yeniden üretilebilir.

Hafta = Pazartesi 00:00 UTC → sonraki Pazartesi. Kol başına: getiri (hafta, başlangıçtan beri), en kötü düşüş, işlem,
ciro, maliyet, fren/veto; Jev A/B farkı; agresif kol ↔ kaynak ortalaması; portföyün haftalık dağıtımı.

Maliyet iki parçadır (`docs/Paper-Tasarim.md` §Maliyet ölçümü):
- **yürütme** = dolum fiyatının gönderim anındaki orta fiyattan aleyhte sapması + ücret (gecikmeli olmayan kararlar),
- **gecikme kayması** = gönderim fiyatının karar (kapanış) fiyatından aleyhte sapması (yalnız gecikmeli kararlar).
`gonderim_fiyati` göç 0008'den önceki emirlerde boştur: o emirler yürütme ölçümüne girmez.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine

from tradebot.canli import dagitici as dg
from tradebot.db import paper_dagitim, paper_emir, paper_emir_olay, paper_karar, paper_kol, paper_kol_olay, paper_ozkaynak


def topla(motor: Engine, hafta_ms: int) -> dict:
    """Haftanın ham kayıtları (hafta sonuna kadar kesilmiş)."""
    bit = hafta_ms + dg.HAFTA_MS
    with motor.connect() as b:
        kollar = {r.kol: {"baslangic_ozkaynak": r.baslangic_ozkaynak, "sinif": r.sinif, "baslangic_ms": r.baslangic_ms}
                  for r in b.execute(select(paper_kol))}
        isaret = defaultdict(list)
        for r in b.execute(select(paper_ozkaynak.c.kol, paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak)
                           .where(paper_ozkaynak.c.zaman_ms < bit).order_by(paper_ozkaynak.c.zaman_ms)):
            isaret[r.kol].append((int(r.zaman_ms), float(r.ozkaynak)))
        kararlar = [dict(kol=r.kol, durum=r.durum, veto=r.ayrinti.get("veto") or [],
                         gecikmeli=bool(r.ayrinti.get("gecikmeli"))) for r in b.execute(
            select(paper_karar.c.kol, paper_karar.c.durum, paper_karar.c.ayrinti)
            .where(paper_karar.c.karar_ms >= hafta_ms, paper_karar.c.karar_ms < bit))]
        dolumlar = [dict(kol=r.kol, miktar=float(r.miktar), fiyat=float(r.fiyat), ucret=float(r.ucret),
                         gonderim=r.gonderim_fiyati, karar_fiyati=float(r.karar_fiyati),
                         gecikmeli=bool((r.ayrinti or {}).get("gecikmeli"))) for r in b.execute(
            select(paper_emir_olay.c.kol, paper_emir_olay.c.miktar, paper_emir_olay.c.fiyat, paper_emir_olay.c.ucret,
                   paper_emir.c.gonderim_fiyati, paper_emir.c.karar_fiyati, paper_karar.c.ayrinti)
            .join(paper_emir, paper_emir.c.id == paper_emir_olay.c.emir_id)
            .outerjoin(paper_karar, paper_karar.c.id == paper_emir.c.karar_id)
            .where(paper_emir_olay.c.tur == "dolum", paper_emir.c.tur == "karar",
                   paper_emir_olay.c.zaman_ms >= hafta_ms, paper_emir_olay.c.zaman_ms < bit))]
        olaylar = [dict(kol=r.kol, tur=r.tur, zaman_ms=r.zaman_ms, ayrinti=r.ayrinti) for r in b.execute(
            select(paper_kol_olay).where(paper_kol_olay.c.zaman_ms >= hafta_ms, paper_kol_olay.c.zaman_ms < bit))]
        dagitim = b.execute(select(paper_dagitim.c.portfoy, paper_dagitim.c.ayrinti)
                            .where(paper_dagitim.c.hafta_ms == hafta_ms)).all()
    return {"hafta_ms": hafta_ms, "kollar": kollar, "isaret": dict(isaret), "kararlar": kararlar, "dolumlar": dolumlar,
            "olaylar": olaylar, "dagitim": {p: a for p, a in dagitim}}


def _kol_ozet(kol: str, bilgi: dict, isaret: list[tuple[int, float]], hafta_ms: int, kararlar: list[dict],
              dolumlar: list[dict], olaylar: list[dict]) -> dict:
    b0 = bilgi["baslangic_ozkaynak"]
    once = [o for t, o in isaret if t < hafta_ms]
    oz_bas = once[-1] if once else b0
    oz_son = isaret[-1][1] if isaret else b0
    tepe, dd = b0, 0.0
    for _, o in isaret:
        tepe = max(tepe, o)
        dd = min(dd, o / tepe - 1)
    ciro = sum(abs(d["miktar"] * d["fiyat"]) for d in dolumlar)
    yur = [d for d in dolumlar if d["gonderim"] and not d["gecikmeli"]]
    yur_not = sum(abs(d["miktar"] * d["fiyat"]) for d in yur)
    yur_bps = (sum((d["fiyat"] / d["gonderim"] - 1) * (1 if d["miktar"] > 0 else -1) * abs(d["miktar"] * d["fiyat"])
                   + d["ucret"] for d in yur) / yur_not * 1e4) if yur_not else None
    gec = [d for d in dolumlar if d["gonderim"] and d["gecikmeli"]]
    gec_not = sum(abs(d["miktar"] * d["fiyat"]) for d in gec)
    gec_bps = (sum((d["gonderim"] / d["karar_fiyati"] - 1) * (1 if d["miktar"] > 0 else -1) * abs(d["miktar"] * d["fiyat"])
                   for d in gec) / gec_not * 1e4) if gec_not else None
    return {"kol": kol, "sinif": bilgi["sinif"], "hafta": oz_son / oz_bas - 1, "toplam": oz_son / b0 - 1, "en_kotu_dusus": dd,
            "ozkaynak": oz_son, "karar": len(kararlar), "islem": len(dolumlar), "ciro": ciro / oz_bas if oz_bas else 0.0,
            "yurutme_bps": yur_bps, "gecikme_bps": gec_bps,
            "fren": sum(k["durum"] != "normal" for k in kararlar), "veto": sum(bool(k["veto"]) for k in kararlar),
            "olay": [o["tur"] for o in olaylar]}


def ozetle(v: dict) -> dict:
    """Ham kayıtlardan rapor (saf)."""
    h = v["hafta_ms"]
    grup = lambda xs: {k: [x for x in xs if x["kol"] == k] for k in v["kollar"]}  # noqa: E731
    kr, dl, ol = grup(v["kararlar"]), grup(v["dolumlar"]), grup(v["olaylar"])
    kollar = [_kol_ozet(k, b, v["isaret"].get(k, []), h, kr[k], dl[k], ol[k]) for k, b in sorted(v["kollar"].items())]
    ad = {k["kol"]: k for k in kollar}
    jev = [{"kol": k, "hafta_fark": ad[k + "+jev"]["hafta"] - ad[k]["hafta"],
            "toplam_fark": ad[k + "+jev"]["toplam"] - ad[k]["toplam"], "veto": ad[k + "+jev"]["veto"]}
           for k in ad if k + "+jev" in ad]
    kaynaklar = [ad[j["kol"]] for j in jev]
    agresif = [{"kol": k, "hafta": ad[k]["hafta"], "kaynak_ort": sum(x["hafta"] for x in kaynaklar) / len(kaynaklar),
                "toplam": ad[k]["toplam"], "kaynak_ort_toplam": sum(x["toplam"] for x in kaynaklar) / len(kaynaklar),
                "en_kotu_dusus": ad[k]["en_kotu_dusus"]}
               for k in ad if k.startswith("agresif@") and kaynaklar]
    return {"hafta_ms": h, "hafta": datetime.fromtimestamp(h / 1000, UTC).date().isoformat(), "kollar": kollar, "jev_ab": jev,
            "agresif": agresif, "dagitim": v["dagitim"]}


def _yuzde(x: float | None, basamak: int = 2) -> str:
    return "—" if x is None else f"{x * 100:+.{basamak}f}%"


def _bps(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}"


def markdown(r: dict) -> str:
    s = [f"# Paper haftalık rapor — {r['hafta']} haftası", "",
         "Kaynak: paper defteri (yeniden üretilebilir: `tradebot paper rapor`). Maliyet bps: yürütme = dolum ↔ gönderim "
         "anındaki orta fiyat + ücret; gecikme = gönderim ↔ karar fiyatı (yalnız gecikmeli kararlar).", "",
         "| Kol | Sınıf | Hafta | Başlangıçtan | En kötü düşüş | Karar | İşlem | Ciro | Yürütme bps | Gecikme bps "
         "| Fren | Veto | Olay |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k in r["kollar"]:
        s.append(f"| `{k['kol']}` | {k['sinif']} | {_yuzde(k['hafta'])} | {_yuzde(k['toplam'])} | "
                 f"{_yuzde(k['en_kotu_dusus'], 1)} | {k['karar']} | {k['islem']} | {k['ciro']:.2f} | "
                 f"{_bps(k['yurutme_bps'])} | {_bps(k['gecikme_bps'])} | {k['fren']} | {k['veto']} | "
                 f"{', '.join(k['olay']) or '—'} |")
    if r["jev_ab"]:
        s += ["", "## Jev A/B (Jev'li − Jev'siz)", "", "| Kol | Hafta farkı | Başlangıçtan farkı | Jev'li kopyada veto |",
              "| --- | --- | --- | --- |"]
        s += [f"| `{j['kol']}` | {_yuzde(j['hafta_fark'], 3)} | {_yuzde(j['toplam_fark'], 3)} | {j['veto']} |"
              for j in r["jev_ab"]]
    for a in r["agresif"]:
        s += ["", "## Agresif gözlem kolu", "",
              f"`{a['kol']}`: hafta {_yuzde(a['hafta'])} (kaynak kolların ortalaması {_yuzde(a['kaynak_ort'])}), "
              f"başlangıçtan {_yuzde(a['toplam'])} ({_yuzde(a['kaynak_ort_toplam'])}), en kötü düşüş "
              f"{_yuzde(a['en_kotu_dusus'], 1)}."]
    for p, d in r["dagitim"].items():
        s += ["", f"## Dağıtım — `{p}`", "",
              f"Dağıtılan kaldıraç {d.get('kaldirac', 0):.2f}x, gölge {d.get('kaldirac_golge', 0):.2f}x, uygun kol "
              f"{len(d.get('uygun', []))}. Ortalama korelasyon: "
              f"{'—' if d.get('korelasyon_ort') is None else format(d['korelasyon_ort'], '.2f')}."]
        satir = [(k, x) for k, x in d.get("kollar", {}).items() if x.get("agirlik") or x.get("katsayi")]
        if satir:
            s += ["", "| Kaynak | Sınıf | Paper günü | Sharpe (küçültülmüş) | Gölge ağırlık | Kademe | Katsayı |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
            s += [f"| `{k}` | {x['sinif']} | {x['gun']:.0f} | {x.get('sharpe', 0):.2f} | {x['agirlik']:.3f} | "
                  f"{x.get('kademe', 0):.2f} | {x['katsayi']:.3f} |" for k, x in satir]
        else:
            s += ["", "Henüz hiçbir kaynak kolun 28 günlük paper geçmişi yok: gölge ağırlık hesaplanmadı."]
    return "\n".join(s) + "\n"


def telegram_ozeti(r: dict) -> str:
    satir = [f"Paper haftası {r['hafta']}"]
    for k in r["kollar"]:
        if k["kol"].endswith("+jev"):
            continue
        satir.append(f"{k['kol'].split('@')[0]}@{k['kol'].rsplit('@', 1)[-1]}: {_yuzde(k['hafta'])} "
                     f"(toplam {_yuzde(k['toplam'])}, DD {_yuzde(k['en_kotu_dusus'], 1)})")
    olay = [f"{k['kol']}: {', '.join(k['olay'])}" for k in r["kollar"] if k["olay"]]
    if olay:
        satir += ["Olaylar:"] + olay
    return "\n".join(satir)


def uret(motor: Engine, veri_dizini, hafta_ms: int) -> tuple[dict, str, object]:
    """Raporu üretir ve `data/rapor/paper-<hafta>.md` olarak yazar. Döndürür: (rapor, markdown, yol)."""
    from pathlib import Path

    r = ozetle(topla(motor, hafta_ms))
    md = markdown(r)
    yol = Path(veri_dizini) / "rapor" / f"paper-{r['hafta']}.md"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(md, encoding="utf-8")
    return r, md, yol


def bekleyen_hafta(veri_dizini, simdi_ms: int, gecikme_ms: int = 30 * 60_000) -> int | None:
    """Raporu henüz yazılmamış, bitmiş son hafta (bittikten `gecikme_ms` sonra; son saatin işareti yazılmış olsun)."""
    from pathlib import Path

    h = dg.hafta_basi(simdi_ms - gecikme_ms) - dg.HAFTA_MS
    ad = datetime.fromtimestamp(h / 1000, UTC).date().isoformat()
    return None if (Path(veri_dizini) / "rapor" / f"paper-{ad}.md").exists() else h
