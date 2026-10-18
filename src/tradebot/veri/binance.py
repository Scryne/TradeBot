"""Binance indiricisi: data.binance.vision arşivi (aylık + günlük zip, yayınlanan SHA-256 ile doğrulanır) ve REST.

Evren: arşivin S3 listelemesindeki TÜM USDT spot sembolleri (kaldırılmışlar dahil → hayatta kalma yanlılığı yok).
Tuzaklar (Spike 03): 2025'ten itibaren zaman damgası mikrosaniye, öncesi milisaniye; bazı dosyalarda başlık satırı.
Ham zip olduğu gibi saklanır; bar deposu hamdan üretilir.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from sqlalchemy.engine import Engine

from tradebot.kayit import log
from tradebot.veri import enstruman as en
from tradebot.veri.depo import BarDepo, HamDepo
from tradebot.veri.http import NazikIstemci, YokHatasi

ARSIV = "https://data.binance.vision"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
KLINE_KOLON = ["acilis", "open", "high", "low", "close", "volume", "kapanis", "quote_volume", "trades",
               "taker_base", "taker_quote", "yok"]
_log = log("veri.binance")


def zaman_birimi_ms(deger: int) -> int:
    """Ham zaman damgasını ms'ye çeviren bölen: > 10^14 ise mikrosaniye (2025+), değilse milisaniye."""
    return 1000 if deger > 10**14 else 1


def kline_zip_oku(icerik: bytes) -> pl.DataFrame:
    with zipfile.ZipFile(io.BytesIO(icerik)) as z:
        ham = z.read(z.namelist()[0])
    ilk = ham.split(b"\n", 1)[0]
    baslik = not ilk[:1].isdigit()
    # Tip çıkarımı yok: bazı dosyalarda ilk satırlar tamsayı görünüp sonradan ondalık geliyor (SOLUSDT perp, 2026-10-06)
    df = pl.read_csv(io.BytesIO(ham), has_header=False, skip_rows=1 if baslik else 0, new_columns=KLINE_KOLON,
                     infer_schema_length=0, schema_overrides={"acilis": pl.Int64, "kapanis": pl.Int64})
    if df.is_empty():
        return df
    bolen = zaman_birimi_ms(int(df["acilis"][0]))
    return df.select((pl.col("acilis") // bolen).alias("acilis_ms"), *[pl.col(k).cast(pl.Float64) for k in
                     ("open", "high", "low", "close", "volume", "quote_volume")], pl.col("trades").cast(pl.Float64))


def funding_zip_oku(icerik: bytes) -> pl.DataFrame:
    with zipfile.ZipFile(io.BytesIO(icerik)) as z:
        df = pl.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    bolen = zaman_birimi_ms(int(df["calc_time"][0]))
    return df.select((pl.col("calc_time") // bolen).alias("zaman_ms"), pl.col("last_funding_rate").cast(pl.Float64).alias("oran"),
                     pl.col("funding_interval_hours").cast(pl.Int64).alias("aralik_saat"))


class Binance:
    def __init__(self, veri_dizini: Path, motor: Engine, evren: dict | None = None) -> None:
        self.ham = HamDepo(veri_dizini, motor)
        self.bar = BarDepo(veri_dizini)
        self.motor = motor
        self.evren = evren or en.evren_yukle()
        self.http = NazikIstemci("binance", aralik_sn=0.05)

    # --- listeleme -------------------------------------------------------------------------------------------------
    def _s3_liste(self, prefix: str, desen: str) -> list[str]:
        out, marker = [], ""
        while True:
            params = {"delimiter": "/", "prefix": prefix} | ({"marker": marker} if marker else {})
            x = self.http.al(S3, params).decode()
            parca = re.findall(desen, x)
            out += parca
            if "<IsTruncated>true</IsTruncated>" not in x or not parca:
                return out
            sonraki = re.findall(r"<NextMarker>(.*?)</NextMarker>", x)
            marker = sonraki[-1] if sonraki else re.findall(r"<(?:Key|Prefix)>(.*?)</(?:Key|Prefix)>", x)[-1]

    def usdt_semboller(self) -> list[str]:
        s = self._s3_liste("data/spot/monthly/klines/", r"<Prefix>data/spot/monthly/klines/([^/]+)/</Prefix>")
        return sorted(x for x in s if x.endswith("USDT"))

    def aylik_dosyalar(self, sembol: str, zd: str, tur: str = "spot/monthly/klines") -> list[str]:
        p = f"data/{tur}/{sembol}/{zd}/" if "klines" in tur else f"data/{tur}/{sembol}/"
        return [k for k in self._s3_liste(p, r"<Key>(.*?)</Key>") if k.endswith(".zip")]

    # --- indirme ---------------------------------------------------------------------------------------------------
    def _indir_dogrula(self, anahtar_s3: str) -> tuple[bytes, str]:
        icerik = self.http.al(f"{ARSIV}/{anahtar_s3}")
        try:
            saglama = self.http.al(f"{ARSIV}/{anahtar_s3}.CHECKSUM").decode().split()[0]
        except YokHatasi:
            saglama = None
        return icerik, saglama

    def klines(self, sembol: str, zd: str, gunluk: bool = True) -> dict:
        """Eksik aylık dosyaları (+ işlemdeyse bu ayın dünkü dahil günlük dosyalarını) indirir, bar deposuna işler.

        Günlük dosyalar listelenmez (sembol başına sayfalı S3 isteği pahalı); adları üretilir, olmayan atlanır.
        """
        kimlik = f"{self.evren['kripto']['piyasa']}:{sembol}"
        yeni, parcalar = 0, []
        adaylar = self.aylik_dosyalar(sembol, zd)
        if gunluk:
            bugun = datetime.now(UTC).date()   # UTC: arşivin günleri UTC
            adaylar += [f"data/spot/daily/klines/{sembol}/{zd}/{sembol}-{zd}-{bugun.year}-{bugun.month:02d}-{g:02d}.zip"
                        for g in range(1, bugun.day)]
        try:
            for anahtar_s3 in adaylar:
                mantiksal = "spot/klines/" + anahtar_s3.split("/klines/", 1)[1].removesuffix(".zip")
                if self.ham.var_mi("binance", mantiksal):
                    continue
                try:
                    icerik, saglama = self._indir_dogrula(anahtar_s3)
                except YokHatasi:
                    continue  # günlük dosya henüz yayınlanmamış ya da sembol işlemde değil
                self.ham.kaydet("binance", mantiksal, icerik, "zip", beklenen_sha=saglama)
                parcalar.append(kline_zip_oku(icerik))
                yeni += 1
        finally:
            # Hama kaydedilen her dosya bara da işlenir: sonraki dosyanın hatası öncekileri kaybettirmesin (sonraki koşu
            # hamda var diye atlar; 2026-10-18 denetimi). Dukascopy'deki kalıpla aynı.
            if parcalar:
                self.bar.yaz(kimlik, zd, pl.concat(parcalar))
        df = self.bar.oku(kimlik, zd)
        return {"kimlik": kimlik, "zd": zd, "yeni_dosya": yeni, "bar": len(df),
                "ilk_ms": int(df["acilis_ms"][0]) if len(df) else None, "son_ms": int(df["acilis_ms"][-1]) if len(df) else None}

    def funding(self, sembol: str) -> dict:
        kimlik = f"BINANCE-UM:{sembol}"
        yeni, parcalar = 0, []
        try:
            for anahtar_s3 in self.aylik_dosyalar(sembol, "", "futures/um/monthly/fundingRate"):
                mantiksal = "um/funding/" + anahtar_s3.rsplit("/", 1)[1].removesuffix(".zip")
                if self.ham.var_mi("binance", mantiksal):
                    continue
                icerik, saglama = self._indir_dogrula(anahtar_s3)
                self.ham.kaydet("binance", mantiksal, icerik, "zip", beklenen_sha=saglama)
                parcalar.append(funding_zip_oku(icerik))
                yeni += 1
        finally:
            self._funding_yaz(sembol, parcalar)
        return {"kimlik": kimlik, "yeni_dosya": yeni}

    def _funding_yaz(self, sembol: str, parcalar: list) -> None:
        if parcalar:
            yol = self.bar.kok.parent / "funding" / f"{sembol}.parquet"
            yol.parent.mkdir(parents=True, exist_ok=True)
            df = pl.concat(parcalar)
            if yol.exists():
                df = pl.concat([pl.read_parquet(yol), df])
            df.unique("zaman_ms", keep="last").sort("zaman_ms").write_parquet(yol)

    def durumlar(self) -> dict[str, str]:
        """exchangeInfo: sembol → durum (TRADING, BREAK …). Listede olmayan = tamamen kaldırılmış."""
        import json
        d = json.loads(self.http.al("https://api.binance.com/api/v3/exchangeInfo"))
        return {s["symbol"]: s["status"] for s in d["symbols"]}

    def evren_guncelle(self, zd: str = "1h", sinir: int | None = None, isci: int = 4) -> list[dict]:
        """Tüm USDT sembollerini indirir, enstrüman kaydını ve tarihsel sınırları günceller.

        `isci` paralel sembol; istek temposu yine tek NazikIstemci'den geçer (kaynak başına sınır korunur).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        durum = self.durumlar()
        semboller = self.usdt_semboller()[:sinir] if sinir else self.usdt_semboller()

        def bir(s: str) -> dict | None:
            try:
                r = self.klines(s, zd, gunluk=durum.get(s) == "TRADING")
            except Exception as e:  # tek sembol hatası evreni durdurmaz
                _log.error("sembol_hatasi", sembol=s, hata=str(e)[:200])
                return None
            en.kaydet(self.motor, [en.kripto_enstrumani(self.evren, s, {"binance_durum": durum.get(s, "YOK")})])
            en.sinir_guncelle(self.motor, r["kimlik"], r["ilk_ms"], r["son_ms"],
                              "aktif" if durum.get(s) == "TRADING" else "islem_disi")
            return r

        sonuc = []
        with ThreadPoolExecutor(max_workers=isci) as h:
            for i, f in enumerate(as_completed([h.submit(bir, s) for s in semboller]), 1):
                if (r := f.result()) is not None:
                    sonuc.append(r)
                if i % 50 == 0:
                    _log.info("evren_ilerleme", tamam=i, toplam=len(semboller))
        return sonuc


def simdi_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)
