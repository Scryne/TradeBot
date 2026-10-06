"""Binance USDT-M arşivi (`data/um/`, kaldırılanlar dahil) üzerinde iki dalga.

Dalga 16 — OI temizlenmesi sonrası dönüş (`cekirdek/oi_donus.py`): saatlik. Olay saatinin kapanışında karar, giriş
sonraki saatin açılışında, çıkış `tut` saat sonra açılışta. Perp uzun; `hedge` ise aynı nominal BTC perp kısa.
Olay başına bacak nominali, girişteki özkaynağın `notional`'ı; açık brüt `azami_brut`'u aşamaz (aşacaksa olay kurulmaz).
Aynı saatte birden çok olay: en sert z önce. Aynı sembolde açık pozisyon varken yeni olay alınmaz.

Dalga 17 — kesitsel funding (`cekirdek/funding_kesit.py`): günlük işaretleme, haftalık yeniden dengeleme. Pozisyonlar
nominal değer olarak tutulur ve fiyatla kayar; yeniden dengelemede maliyet |hedef − mevcut| üzerinden.

Funding: tutulan nominal × oran; uzun öder, kısa alır (oran pozitifse). Ödeme anı pozisyonun açık olduğu
(giriş, çıkış] aralığındaysa yazılır. Ücret + kayma giriş ve çıkışta, aleyhte (kural 4).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from tradebot.arastirma.kilit_dalga import _ms, _ozet, degerlendir, plan_ac
from tradebot.arastirma.metrik import HAFTA_MS, PAZARTESI_KAYMA_MS
from tradebot.cekirdek import funding_kesit as fk
from tradebot.cekirdek import oi_donus as od

SAAT_MS = 3_600_000
GUN_MS = 86_400_000
AZAMI_TUT = 24


def _taban(sembol: str) -> str:
    t = sembol.removesuffix("USDT")
    for on in ("1000000", "1000", "1M"):
        if t.startswith(on) and len(t) > len(on):
            return t[len(on):]
    return t


def _veri_hash(dizin: Path) -> str:
    """Türev dosyaların adı + boyutu + mtime'ı değil içeriği: hamdan yeniden üretilebilir, içerik kimliktir."""
    h = hashlib.sha256()
    for y in sorted(dizin.rglob("*.parquet")):
        h.update(y.relative_to(dizin).as_posix().encode())
        h.update(hashlib.sha256(y.read_bytes()).digest())
    return h.hexdigest()


def _haftalik(t_ms: np.ndarray, r: np.ndarray, bas: int, bit: int) -> np.ndarray:
    h0 = (bas - PAZARTESI_KAYMA_MS) // HAFTA_MS
    n = int((bit - PAZARTESI_KAYMA_MS) // HAFTA_MS - h0)
    i = ((t_ms - PAZARTESI_KAYMA_MS) // HAFTA_MS - h0).astype(int)
    ok = (i >= 0) & (i < n)
    lg = np.zeros(n)
    np.add.at(lg, i[ok], np.log1p(r[ok]))
    return np.expm1(lg)


def _yillar(t_ms: np.ndarray, r: np.ndarray, bas: int, bit: int) -> dict[int, float]:
    out = {}
    for y in range(datetime.fromtimestamp(bas / 1000, UTC).year, datetime.fromtimestamp(bit / 1000, UTC).year + 1):
        m = (t_ms >= _ms(f"{y}-01-01")) & (t_ms < _ms(f"{y + 1}-01-01"))
        out[y] = float(np.expm1(np.log1p(r[m]).sum())) if m.any() else 0.0
    return out


def _kol(ad: str, dosya: str, p: dict, t: np.ndarray, r: np.ndarray, r2: np.ndarray, olay: dict, d: dict,
         t0: float) -> dict:
    bas, is_bit, bit = _ms(d["donem"]["bas"]), _ms(d["donem"]["is_bitis"]), _ms(d["donem"]["bit"])
    h = _haftalik(t, r, bas, bit)
    ks = int((is_bit - PAZARTESI_KAYMA_MS) // HAFTA_MS - (bas - PAZARTESI_KAYMA_MS) // HAFTA_MS)
    return {"p": p, "h": h, "tam": _ozet(h), "is": _ozet(h[:ks]), "kor": _ozet(h[ks:]),
            "stres": _ozet(_haftalik(t, r2, bas, bit)), "yillik": _yillar(t, r, bas, bit), "olay": olay,
            "sure": time.perf_counter() - t0, "ad": ad, "dosya": dosya}


def _olay_ozet(g: list[float], kurulmadi: dict[str, int]) -> dict:
    a = np.asarray(g)
    return {"toplam": len(a) + sum(kurulmadi.values()), "kurulan": len(a),
            "kurulmadi": [{"kurulmadi": k, "len": v} for k, v in sorted(kurulmadi.items())],
            "birim_ort": float(a.mean()) if len(a) else None, "birim_medyan": float(np.median(a)) if len(a) else None,
            "isabet": float((a > 0).mean()) if len(a) else None,
            "birim_t": float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))) if len(a) > 2 else None}


# --- Dalga 16 ------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Aday:
    t_ms: int                 # olay saatinin açılışı (karar bu saatin kapanışında)
    sembol: str
    z: float
    doi: float
    acilis: np.ndarray        # o[t+1 .. t+1+AZAMI_TUT] (eksikse NaN)
    funding: tuple[tuple[int, float], ...]   # (zaman_ms, oran), t+1 açılışından sonraki AZAMI_TUT saat


def _izgara_saat(b: pl.DataFrame) -> tuple[int, dict[str, np.ndarray]]:
    t0 = int(b["acilis_ms"].min())
    n = int((int(b["acilis_ms"].max()) - t0) // SAAT_MS) + 1
    i = ((b["acilis_ms"].to_numpy() - t0) // SAAT_MS).astype(int)
    out = {}
    for k in ("open", "close", "quote_volume"):
        a = np.full(n, np.nan)
        a[i] = b[k].to_numpy()
        out[k] = a
    return t0, out


def adaylar(kok: Path, k: float, asgari_hacim: float, bas: int, bit: int) -> tuple[list[Aday], dict]:
    """Fiyat ve hacim koşulunu geçen her (sembol, saat); OI koşulu ızgarada ayrıca uygulanır. + BTC açılış dizisi."""
    out: list[Aday] = []
    btc = None
    for y in sorted((kok / "1h").glob("*.parquet")):
        s = y.stem
        b = pl.read_parquet(y).unique("acilis_ms").sort("acilis_ms")
        if b.height < od.PENCERE + 2:
            continue
        t0, a = _izgara_saat(b)
        if s == "BTCUSDT":
            btc = (t0, a["open"])
        oi = np.full(len(a["open"]), np.nan)
        yo = kok / "oi" / f"{s}.parquet"
        if yo.exists():
            o = pl.read_parquet(yo)
            j = ((o["acilis_ms"].to_numpy() - t0) // SAAT_MS).astype(int)
            ok = (j >= 0) & (j < len(oi))
            oi[j[ok]] = o["oi"].to_numpy()[ok]
        f = od.ozellik(a["open"], a["close"], a["quote_volume"], oi)
        tt = t0 + np.arange(len(oi)) * SAAT_MS
        with np.errstate(invalid="ignore"):
            m = (f["z"] <= -k) & (f["hacim"] >= asgari_hacim) & (tt >= bas) & (tt < bit)
        if not m.any():
            continue
        yf = kok / "funding" / f"{s}.parquet"
        fd = pl.read_parquet(yf).sort("zaman_ms") if yf.exists() else pl.DataFrame({"zaman_ms": [], "oran": []})
        fz, fo = fd["zaman_ms"].to_numpy(), fd["oran"].to_numpy()
        for i in np.flatnonzero(m):
            ac = a["open"][i + 1: i + 2 + AZAMI_TUT]
            ac = np.r_[ac, np.full(AZAMI_TUT + 1 - len(ac), np.nan)]
            g0 = int(tt[i]) + SAAT_MS
            w = (fz > g0) & (fz <= g0 + AZAMI_TUT * SAAT_MS)
            out.append(Aday(int(tt[i]), _taban(s), float(f["z"][i]), float(f["doi"][i]), ac,
                            tuple(zip(fz[w].tolist(), fo[w].tolist(), strict=True))))
    if btc is None:
        raise ValueError("BTCUSDT 1h verisi yok")
    yf = kok / "funding" / "BTCUSDT.parquet"
    bf = pl.read_parquet(yf).sort("zaman_ms")
    return sorted(out, key=lambda x: (x.t_ms, x.z, x.sembol)), {"t0": btc[0], "open": btc[1],
                                                                 "fz": bf["zaman_ms"].to_numpy(),
                                                                 "fo": bf["oran"].to_numpy()}


def donus_kos(aday: list[Aday], btc: dict, kural: od.DonusKural, hedge: bool, notional: float, azami_brut: float,
              maliyet: dict, bas: int, bit: int) -> tuple[np.ndarray, np.ndarray, list[float], dict[str, int]]:
    """Döndürür: (saat_ms, saatlik özkaynak getirisi, olay birim getirileri, kurulmayan sayıları)."""
    n_saat = int((bit - bas) // SAAT_MS)
    gir_brut = np.zeros(n_saat)
    olaylar: list[tuple[int, int, np.ndarray]] = []   # (giriş saati indeksi, tut, saatlik birim getiri)
    birim, kurulmadi = [], {}
    acik_bitis: dict[str, int] = {}
    bo, b0 = btc["open"], btc["t0"]
    c_tok = maliyet["ucret"] + maliyet["kayma_token"]
    c_btc = maliyet["ucret"] + maliyet["kayma_btc"]
    bacak = 2 if hedge else 1
    for e in aday:
        if not od.olay_mu(e.z, e.doi, kural.asgari_hacim, kural) or (hedge and e.sembol == "BTC"):
            continue
        gi = int((e.t_ms + SAAT_MS - bas) // SAAT_MS)
        if gi < 0 or gi + kural.tut >= n_saat:
            continue
        if acik_bitis.get(e.sembol, -1) > gi:
            kurulmadi["sembol_acik"] = kurulmadi.get("sembol_acik", 0) + 1
            continue
        if gir_brut[gi] + bacak * notional > azami_brut + 1e-12:
            kurulmadi["tavan"] = kurulmadi.get("tavan", 0) + 1
            continue
        o = e.acilis[: kural.tut + 1]
        bj = int((e.t_ms + SAAT_MS - b0) // SAAT_MS)
        b = bo[bj: bj + kural.tut + 1] if bj >= 0 else np.array([])
        if np.isnan(o).any() or (hedge and (len(b) < kural.tut + 1 or np.isnan(b).any())):
            kurulmadi["fiyat_eksik"] = kurulmadi.get("fiyat_eksik", 0) + 1
            continue
        u = np.diff(o) / o[0]
        if hedge:
            u = u - np.diff(b) / b[0]
        g0 = e.t_ms + SAAT_MS
        for z, oran in e.funding:
            if z <= g0 + kural.tut * SAAT_MS:
                u[min(int((z - g0 - 1) // SAAT_MS), kural.tut - 1)] -= oran
        if hedge:
            w = (btc["fz"] > g0) & (btc["fz"] <= g0 + kural.tut * SAAT_MS)
            for z, oran in zip(btc["fz"][w], btc["fo"][w], strict=True):
                u[min(int((z - g0 - 1) // SAAT_MS), kural.tut - 1)] += oran
        mal = c_tok + (c_btc if hedge else 0.0)
        u[0] -= mal
        u[-1] -= mal
        olaylar.append((gi, kural.tut, u))
        gir_brut[gi: gi + kural.tut] += bacak * notional
        acik_bitis[e.sembol] = gi + kural.tut
        birim.append(float(u.sum()))
    # Özkaynakla ölçekleme: olay nominali girişteki özkaynağın `notional`'ı; saatlik getiri = Σ pnl / önceki özkaynak
    giren: dict[int, list[tuple[int, np.ndarray]]] = {}
    for gi, tut, u in olaylar:
        giren.setdefault(gi, []).append((tut, u))
    E, r = 1.0, np.zeros(n_saat)
    nominal: list[tuple[int, int, float, np.ndarray]] = []
    for h in range(n_saat):
        for tut, u in giren.get(h, ()):
            nominal.append((h, tut, notional * E, u))
        if not nominal:
            continue
        p = sum(N * u[h - g] for g, tut, N, u in nominal)
        r[h] = p / E
        E += p
        nominal = [x for x in nominal if h + 1 < x[0] + x[1]]
    return bas + np.arange(n_saat) * SAAT_MS, r, birim, kurulmadi


def dalga16(d: dict, veri_dizini: Path, defter, dosya: Path) -> list[dict]:
    kok = Path(veri_dizini) / "um"
    bas, bit = _ms(d["donem"]["bas"]), _ms(d["donem"]["bit"])
    k = float(d["kural"]["k"])
    asgari = float(d["kural"]["asgari_hacim"])
    aday, btc = adaylar(kok, k, asgari, bas - AZAMI_TUT * SAAT_MS, bit)
    vh = _veri_hash(kok)
    plan_ac(d, dosya, defter, ["BINANCEUM:perp"])
    mal = d["maliyet"]
    stres = {x: v * d["olcut"]["stres_maliyet"] for x, v in mal.items()}
    kollar = []
    from tradebot.arastirma.dogrulama import izgara
    for p in izgara(d["izgara"]):
        t0 = time.perf_counter()
        oi = None if p["oi_esik"] in (None, "yok") else float(p["oi_esik"])
        kural = od.DonusKural(k=k, oi_esik=oi, tut=int(p["tut"]), asgari_hacim=asgari)
        t, r, birim, km = donus_kos(aday, btc, kural, bool(p["hedge"]), d["notional"], d["azami_brut"], mal, bas, bit)
        _, r2, _, _ = donus_kos(aday, btc, kural, bool(p["hedge"]), d["notional"], d["azami_brut"], stres, bas, bit)
        ad = f"oi_donus(oi={oi},tut={kural.tut},hedge={int(bool(p['hedge']))})"
        kollar.append(_kol(ad, f"oi_donus_o{oi}_t{kural.tut}_h{int(bool(p['hedge']))}", p, t, r, r2,
                           _olay_ozet(birim, km), d, t0))
    return degerlendir(kollar, d, veri_dizini, defter, "BINANCEUM:oi_donus", "1h", vh)


# --- Dalga 17 ------------------------------------------------------------------------------------------------------
def gunluk_panel(kok: Path) -> tuple[dict[str, dict[int, tuple[float, float, float]]], dict[str, dict[int, float]]]:
    """{taban: {gun_ms: (gün açılışı, günün son kapanışı, gün quote hacmi)}}, {taban: {gun_ms: gün funding toplamı}}.

    Gün açılışı yalnız 00:00 saatlik barı varsa tanımlıdır (yoksa o gün işlem görmüyor sayılır)."""
    fiyat, fund = {}, {}
    for y in sorted((kok / "1h").glob("*.parquet")):
        s = _taban(y.stem)
        if s in fiyat:   # çarpanlı ve çarpansız aynı taban: ilk (alfabetik) kalır
            continue
        b = (pl.read_parquet(y).unique("acilis_ms").sort("acilis_ms")
             .with_columns(gun=pl.col("acilis_ms") // GUN_MS * GUN_MS))
        g = b.group_by("gun", maintain_order=True).agg(
            pl.col("open").filter(pl.col("acilis_ms") == pl.col("gun")).first().alias("acilis"),
            pl.col("close").last(), pl.col("quote_volume").sum())
        fiyat[s] = {int(a): (float("nan") if o is None else float(o), float(c), float(q))
                    for a, o, c, q in g.iter_rows()}
        yf = kok / "funding" / f"{y.stem}.parquet"
        if yf.exists():
            f = pl.read_parquet(yf).with_columns(gun=(pl.col("zaman_ms") - 1) // GUN_MS * GUN_MS)
            f = f.group_by("gun").agg(pl.col("oran").sum())
            fund[s] = dict(zip(f["gun"].to_list(), f["oran"].to_list(), strict=True))
    return fiyat, fund


def kesit_kos(fiyat: dict, fund: dict, kural: fk.KesitKural, maliyet: dict, bas: int, bit: int
              ) -> tuple[np.ndarray, np.ndarray, list[float], dict[str, int]]:
    """Günlük (açılıştan açılışa) özkaynak getirisi. Funding günü: (gün, gün+1] içinde ödenenler → `gun` anahtarı.

    Sinyal: (d − pencere − 1, d − 1] günlerinin funding'i; tam `d` 00:00'da ödenen oran karar anında sınırda
    olduğu için kullanılmaz. Pozisyon günü `d` açılışında kurulur; `d+1` açılışı yoksa (işlem durdu) günün son
    kapanışından kapanır."""
    c = maliyet["ucret"] + maliyet["kayma_token"]
    gunler = np.arange(bas, bit, GUN_MS)
    r = np.zeros(len(gunler))
    v: dict[str, float] = {}
    E = 1.0
    devir, kurulmadi = [], {}
    for i, d in enumerate(gunler):
        d = int(d)
        E0, maliyet_g = E, 0.0
        if (d - PAZARTESI_KAYMA_MS) % HAFTA_MS == 0:
            hacim, ort = {}, {}
            for s, fs in fiyat.items():
                if not np.isfinite(fs.get(d, (np.nan,))[0]):
                    continue
                gec = [fs.get(d - j * GUN_MS) for j in range(1, 31)]
                if any(x is None for x in gec):
                    continue
                hacim[s] = sum(x[2] for x in gec) / 30
                fd = fund.get(s, {})
                fv = [fd[d - j * GUN_MS] for j in range(2, kural.pencere + 2) if d - j * GUN_MS in fd]
                if fv:
                    ort[s] = sum(fv) / kural.pencere
            w = fk.agirliklar(hacim, ort, kural)
            if not w:
                kurulmadi["evren_kucuk"] = kurulmadi.get("evren_kucuk", 0) + 1
            hedef = {s: x * E for s, x in w.items()}
            dv = sum(abs(hedef.get(s, 0.0) - v.get(s, 0.0)) for s in set(hedef) | set(v))
            maliyet_g = dv * c          # yeniden dengeleme maliyeti o günün getirisine yazılır
            E -= maliyet_g
            devir.append(dv / max(E0, 1e-12))
            v = hedef
        if not v:
            r[i] = -maliyet_g / E0
            continue
        p = 0.0
        yeni = {}
        for s, x in v.items():
            o0 = fiyat[s][d][0] if d in fiyat[s] else np.nan
            sonraki = fiyat[s].get(d + GUN_MS)
            if not np.isfinite(o0):
                kurulmadi["fiyat_eksik"] = kurulmadi.get("fiyat_eksik", 0) + 1
                continue
            if sonraki is not None and np.isfinite(sonraki[0]):
                g = sonraki[0] / o0 - 1
                p += x * g - x * fund.get(s, {}).get(d, 0.0)
                yeni[s] = x * (1 + g)
            else:   # işlem durdu: günün son kapanışından çık, çıkış maliyeti
                g = fiyat[s][d][1] / o0 - 1
                p += x * g - abs(x * (1 + g)) * c
                kurulmadi["islem_durdu"] = kurulmadi.get("islem_durdu", 0) + 1
        r[i] = (p - maliyet_g) / E0
        E += p
        v = yeni
    return gunler, r, devir, kurulmadi


def dalga17(d: dict, veri_dizini: Path, defter, dosya: Path) -> list[dict]:
    kok = Path(veri_dizini) / "um"
    bas, bit = _ms(d["donem"]["bas"]), _ms(d["donem"]["bit"])
    fiyat, fund = gunluk_panel(kok)
    vh = _veri_hash(kok)
    plan_ac(d, dosya, defter, ["BINANCEUM:perp"])
    mal = d["maliyet"]
    stres = {x: v * d["olcut"]["stres_maliyet"] for x, v in mal.items()}
    kollar = []
    from tradebot.arastirma.dogrulama import izgara
    for p in izgara(d["izgara"]):
        t0 = time.perf_counter()
        kural = fk.KesitKural(pencere=int(p["pencere"]), n=int(p["n"]), evren=int(d["evren"]), brut=float(d["brut"]))
        t, r, devir, km = kesit_kos(fiyat, fund, kural, mal, bas, bit)
        _, r2, _, _ = kesit_kos(fiyat, fund, kural, stres, bas, bit)
        olay = {"toplam": len(devir), "kurulan": len(devir), "kurulmadi": [{"kurulmadi": a, "len": b}
                                                                        for a, b in sorted(km.items())],
                "ort_haftalik_devir": float(np.mean(devir)) if devir else None}
        kollar.append(_kol(f"funding_kesit(pencere={kural.pencere},n={kural.n})",
                           f"funding_kesit_p{kural.pencere}_n{kural.n}", p, t, r, r2, olay, d, t0))
    return degerlendir(kollar, d, veri_dizini, defter, "BINANCEUM:funding_kesit", "1d", vh)


def kos(dosya: Path, veri_dizini: Path, defter=None) -> list[dict]:
    d = yaml.safe_load(Path(dosya).read_text(encoding="utf-8"))
    return {"oi_donus": dalga16, "funding_kesit": dalga17}[d["motor"]](d, veri_dizini, defter, Path(dosya))


def ozet_yaz(sonuc: list[dict]) -> str:
    return json.dumps([{x: r[x] for x in ("kol", "karar", "dsr", "tam", "kor", "olay", "yillik")} for r in sonuc],
                      ensure_ascii=False, indent=1, default=str)
