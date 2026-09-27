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


def topla(motor: Engine, hafta_ms: int, bit_ms: int | None = None) -> dict:
    """[hafta_ms, bit_ms) döneminin ham kayıtları (varsayılan: bir hafta); işaretler dönem sonuna kadar kesilmiş."""
    bit = bit_ms or hafta_ms + dg.HAFTA_MS
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


def maliyet_bps(dolumlar: list[dict]) -> tuple[float | None, float | None]:
    """(yürütme, gecikme kayması) bps, notional ağırlıklı, aleyhte pozitif. Bkz. modül açıklaması."""
    def _not(d: dict) -> float:
        return abs(d["miktar"] * d["fiyat"])

    def _yon(d: dict) -> int:
        return 1 if d["miktar"] > 0 else -1

    yur = [d for d in dolumlar if d["gonderim"] and not d["gecikmeli"]]
    yn = sum(map(_not, yur))
    yur_bps = sum((d["fiyat"] / d["gonderim"] - 1) * _yon(d) * _not(d) + d["ucret"] for d in yur) / yn * 1e4 if yn else None
    gec = [d for d in dolumlar if d["gonderim"] and d["gecikmeli"]]
    gn = sum(map(_not, gec))
    gec_bps = sum((d["gonderim"] / d["karar_fiyati"] - 1) * _yon(d) * _not(d) for d in gec) / gn * 1e4 if gn else None
    return yur_bps, gec_bps


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
    yur_bps, gec_bps = maliyet_bps(dolumlar)
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


def ilk_acilis(motor: Engine) -> int | None:
    from sqlalchemy import func

    with motor.connect() as b:
        return b.execute(select(func.min(paper_kol.c.baslangic_ms))).scalar()


def uret(motor: Engine, veri_dizini, hafta_ms: int) -> tuple[dict, str, object]:
    """Raporu üretir ve `data/rapor/paper-<hafta>.md` olarak yazar. Döndürür: (rapor, markdown, yol)."""
    from pathlib import Path

    r = ozetle(topla(motor, hafta_ms))
    md = markdown(r)
    yol = Path(veri_dizini) / "rapor" / f"paper-{r['hafta']}.md"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(md, encoding="utf-8")
    return r, md, yol


def bekleyen_hafta(veri_dizini, simdi_ms: int, ilk_ms: int | None, gecikme_ms: int = 30 * 60_000) -> int | None:
    """Raporu henüz yazılmamış, bitmiş son hafta (bittikten `gecikme_ms` sonra; son saatin işareti yazılmış olsun).
    `ilk_ms`: ilk paper kolunun açılışı; ondan önce biten hafta raporlanmaz (boş rapor)."""
    from pathlib import Path

    h = dg.hafta_basi(simdi_ms - gecikme_ms) - dg.HAFTA_MS
    if ilk_ms is None or h + dg.HAFTA_MS <= ilk_ms:
        return None
    ad = datetime.fromtimestamp(h / 1000, UTC).date().isoformat()
    return None if (Path(veri_dizini) / "rapor" / f"paper-{ad}.md").exists() else h


GUN_MS = 86_400_000


def gunluk_ozet(motor: Engine, simdi_ms: int, saglik_satiri: str = "") -> str:
    """Günlük Telegram özeti (Faz 9): son 24 saat. Kol getirileri defterden (haftalık raporla aynı hesap), yeni Jev
    olayları, gece işinin son sonucu. Jev'li kopyalar A/B farkı varsa gösterilir (yoksa kalabalık yapmaz)."""
    from tradebot.db import denetim_izi, olay

    r = ozetle(topla(motor, simdi_ms - GUN_MS, simdi_ms))
    ad = {k["kol"]: k for k in r["kollar"]}
    tarih = datetime.fromtimestamp(simdi_ms / 1000, UTC).date().isoformat()
    satir = [f"Günlük özet · {tarih}"]
    if saglik_satiri:
        satir.append(saglik_satiri)
    satir.append("Kollar (24 saat · başlangıçtan):")
    for k in r["kollar"]:
        if k["kol"].endswith("+jev"):
            continue
        j = ad.get(k["kol"] + "+jev")
        ab = f" · Jev farkı {_yuzde(j['hafta'] - k['hafta'])}" if j and abs(j["hafta"] - k["hafta"]) > 1e-9 else ""
        satir.append(f"• {k['kol']}: {_yuzde(k['hafta'])} · {_yuzde(k['toplam'])}{ab}")
    islem = sum(k["islem"] for k in r["kollar"])
    fren = sum(k["fren"] for k in r["kollar"])
    olaylar = [f"{k['kol']}: {', '.join(k['olay'])}" for k in r["kollar"] if k["olay"]]
    satir.append(f"İşlem {islem} · frenli karar {fren}" + (f" · kol olayı: {'; '.join(olaylar)}" if olaylar else ""))
    bas = datetime.fromtimestamp((simdi_ms - GUN_MS) / 1000, UTC)
    with motor.connect() as b:
        yeni = b.execute(select(olay.c.tur, olay.c.rol, olay.c.enstruman).where(olay.c.zaman >= bas)).all()
        gece = b.execute(select(denetim_izi.c.zaman, denetim_izi.c.veri).where(denetim_izi.c.olay == "gece_isi")
                         .order_by(denetim_izi.c.zaman.desc()).limit(1)).first()
    if yeni:
        say = defaultdict(int)
        for tur, rol, _ in yeni:
            say[f"{rol} {tur}"] += 1
        vetolu = sorted({e for t, _, e in yeni if t == "veto"})
        satir.append("Jev: " + ", ".join(f"{k} {v}" for k, v in sorted(say.items()))
                     + (f" ({', '.join(vetolu[:8])}{' …' if len(vetolu) > 8 else ''})" if vetolu else ""))
    else:
        satir.append("Jev: yeni olay yok")
    if gece is not None:
        hatali = [ad_ for ad_, v in gece.veri.items() if isinstance(v, dict) and "hata" in v and v["hata"]
                  and not isinstance(v["hata"], list)]
        satir.append(f"Gece işi {gece.zaman:%H:%M} UTC: " + ("tamam" if not hatali else f"HATALI adım: {', '.join(hatali)}"))
    return "\n".join(satir)
