"""Zekâ servisi: toplayıcılar → roller → olaylar. Tek tur `tur()`, servis döngüsü CLI'dan (`tradebot zeka calis`).

Rol = kaynak başına bir modül (`ROLLER`): `ROL`, `KAYNAK`, `ONEK`, `SORULAR`, `ETKI`, `VETO`, `evren(motor)`,
`hedefler(metin, evren)`, `hedef_state(metin, kimlik)`, `veto_suresi_ms(secim, ayar)`, `bilgi_olayi(secim)`.
Karar kuralı ortaktır (`zeka.karar`).

Çökme güvenliği: yargısı olan (metin, enstrüman) çifti tekrar sorulmaz; yargısı olmayan sonraki turda yeniden ele alınır.
Bir toplayıcının hatası diğerlerini ve rolleri durdurmaz.

Model yok (Jev hata verdi VE yükseltme de cevap vermedi; kural 8 "belirsizlikte riski azalt ve alarm ver"): canlı metinde
`ONLEM_VETO_MS` süreli önlem vetosu + hata logu (bekçi → Telegram KRİTİK). Metin sonraki turda yeniden sorulur, gerçek
yargı gelince kalıcı karar ayrıca yazılır; önlem vetosu süresi dolunca kendiliğinden biter (A2'nin süreli vetosu gibi).
Geçmiş doldurmada önlem vetosu yazılmaz (backtest'e kesintiye bağlı, yeniden üretilemez veto girmesin). 2026-09-28
denetimi: önceden bu durumda veto yazılmıyor, her turda yeni bir "uyarı" satırı birikiyor ve alarm gitmiyordu.
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml
from sqlalchemy import func, select, tuple_
from sqlalchemy.engine import Engine

from tradebot.db import jev_yargi, metin
from tradebot.db import olay as olay_t
from tradebot.kayit import log
from tradebot.metin.binance_duyuru import BinanceDuyuru
from tradebot.metin.kap import KapBildirim
from tradebot.metin.rss import RssToplayici
from tradebot.veri.depo import HamDepo
from tradebot.zeka import a1_binance as a1
from tradebot.zeka import a2_kap as a2
from tradebot.zeka import a3_sec as a3
from tradebot.zeka import olay
from tradebot.zeka.jev import JevIstemci
from tradebot.zeka.karar import karar
from tradebot.zeka.yukseltme import Yukseltme

AYAR_YOLU = Path(__file__).resolve().parents[3] / "config" / "zeka.yaml"
CANLI_PENCERE_MS = 10 * 60_000
ONLEM_VETO_MS = 6 * 3_600_000
ROLLER = {a1.KAYNAK: a1, a2.KAYNAK: a2, a3.KAYNAK: a3}
ROL_ADI = {r.ROL: r for r in ROLLER.values()}
_log = log("zeka.servis")


def ayar_oku(yol: Path = AYAR_YOLU) -> dict:
    return yaml.safe_load(Path(yol).read_text(encoding="utf-8"))


class Zeka:
    def __init__(self, motor: Engine, jev: JevIstemci, yukseltme: Yukseltme, toplayicilar: list, ayar: dict) -> None:
        self.motor, self.jev, self.yuk, self.toplayicilar, self.ayar = motor, jev, yukseltme, toplayicilar, ayar
        self._onlem: dict[tuple[int, str], int] = {}   # (metin, enstrüman) → önlem vetosunun bitişi (ms)

    def _sorulmus(self, rol, metin_id: int) -> set[str]:
        with self.motor.connect() as b:
            hedefler = b.execute(select(jev_yargi.c.hedef).where(
                jev_yargi.c.rol == rol.ROL, jev_yargi.c.saglayici == "jev", jev_yargi.c.hata.is_(None),  # hatalı yeniden
                jev_yargi.c.hedef.like(f"metin:{metin_id}|%"))).scalars()
            return {h.split("|", 1)[1] for h in hedefler}

    def _veto_yaz(self, rol, kimlik: str, gecerli: int, secim: str | None, neden: str, m, yargi_id: int | None,
                  ayrinti: dict) -> int:
        sure = rol.veto_suresi_ms(secim, self.ayar)
        return olay.yaz(self.motor, "veto", kimlik, gecerli, f"{rol.ONEK} {neden}: {m.baslik[:200]}", rol.ROL, m.id,
                        yargi_id, gecerli + sure if sure else None, ayrinti)

    def rol_metin(self, rol, m, evren: set[str], simdi_ms: int) -> list[int]:
        """Bir metni rolüyle değerlendirir. Döndürür: yazılan olay id'leri."""
        hedefler = rol.hedefler(m, evren)
        if not hedefler:
            return []
        esik = float(self.ayar["jev"]["esik"])
        sorulmus = self._sorulmus(rol, m.id)
        canli = simdi_ms - m.yayin_ms < CANLI_PENCERE_MS
        gecerli = simdi_ms if canli else m.yayin_ms + olay.GERIYE_DONUK_GECIKME_MS
        olaylar = []
        for kimlik in hedefler:
            if kimlik in sorulmus:
                continue
            st = rol.hedef_state(m, kimlik)
            hedef = f"metin:{m.id}|{kimlik}"
            y = self.jev.sor(rol.ROL, hedef, st, rol.SORULAR)
            secim, guven, p = y.secim("etki")
            # Kodla denetlenebilen çelişki (rolün `celiski` kancası): karar belirsiz sayılır, yükseltmeye gider
            cel = None if y.hata else getattr(rol, "celiski", lambda *_: None)(secim, m, kimlik)
            guven_k = 0.0 if cel else guven
            yuk, yuk_model = (None, None)
            if y.hata or guven_k < esik:
                yuk, yuk_model = self.yuk.sec(rol.ROL, hedef, rol.ETKI.model_dump(mode="json"), st, "etki")
            if y.hata and yuk is None:   # model yok: önlem vetosu + alarm; metin sonraki turda yeniden sorulur
                # Kesintide birikmiş kuyruğun arkasında kalan yeni duyuru 10 dk'lık canlı pencereyi kaçırabilir: önlem
                # penceresi yayından itibaren ONLEM_VETO_MS. Model hâlâ yoksa süresi dolan önlem yenilenir (2026-10-18).
                onlem_bit = self._onlem.get((m.id, kimlik), 0)
                if simdi_ms - m.yayin_ms < ONLEM_VETO_MS and simdi_ms >= onlem_bit:
                    self._onlem[(m.id, kimlik)] = simdi_ms + ONLEM_VETO_MS
                    olaylar.append(olay.yaz(self.motor, "veto", kimlik, simdi_ms,
                                            f"{rol.ONEK} önlem: model yanıt vermedi: {m.baslik[:200]}", rol.ROL, m.id,
                                            y.id, simdi_ms + ONLEM_VETO_MS,
                                            {"onlem": True, "jev_hata": y.hata[:200], "baslik": m.baslik[:200]}))
                    _log.error("model_yok_onlem_veto", rol=rol.ROL, enstruman=kimlik, metin_id=m.id, hata=y.hata[:200])
                elif not canli:
                    _log.warning("model_yok_gecmis", rol=rol.ROL, enstruman=kimlik, metin_id=m.id)
                continue
            veto, neden = karar(None if y.hata else secim, guven_k, p, yuk, self.yuk.hazir, rol.VETO, esik)
            belirsiz = neden.startswith("belirsiz")
            son_secim = yuk if yuk is not None else secim
            ayrinti = {"jev": secim, "guven": guven, "yukseltme": yuk, "yukseltme_model": yuk_model, "canli": canli,
                       "aciliyet": (y.cevap.get("aciliyet") or {}).get("score"), "baslik": m.baslik[:200]}
            if cel:
                ayrinti["celiski"] = cel
            if veto:
                olaylar.append(self._veto_yaz(rol, kimlik, gecerli, son_secim, neden, m, y.id, ayrinti))
                _log.info("veto", rol=rol.ROL, enstruman=kimlik, neden=neden, canli=canli)
            if belirsiz:
                olaylar.append(olay.yaz(self.motor, "uyari", kimlik, gecerli, f"{rol.ONEK} belirsiz karar: {neden}",
                                        rol.ROL, m.id, y.id, None, ayrinti))
                _log.warning("belirsiz", rol=rol.ROL, enstruman=kimlik, neden=neden)
            bilgi = rol.bilgi_olayi(son_secim) if not veto else None
            if bilgi:
                olaylar.append(olay.yaz(self.motor, bilgi, kimlik, gecerli, f"{rol.ONEK} {neden}: {m.baslik[:200]}",
                                        rol.ROL, m.id, y.id, None, ayrinti))
        return olaylar

    def belirsizleri_yukselt(self) -> dict:
        """Yükseltme modeli yokken belirsiz kalan kararları yükseltme modeline sorar. Yalnız veto EKLER.

        Belirsiz yoldan önceden yazılmış veto, yükseltme "veto gerekmez" dese de kalır: kaldırmak riski artırır
        (kural 5/7; kaldırma yalnız onaylı `veto-kaldir`). Yeni vetonun geçerlilik anı: geçmiş metinde uyarınınki
        (yayın + gecikme), canlıda şimdi. Başarılı yükseltmesi olan (metin, enstrüman) çifti tekrar sorulmaz.
        """
        if not self.yuk.hazir:
            return {"hazir": False}
        simdi = int(time.time() * 1000)
        roller = list(ROL_ADI)
        with self.motor.connect() as b:
            uyarilar = list(b.execute(select(olay_t).where(olay_t.c.tur == "uyari", olay_t.c.rol.in_(roller))
                                      .order_by(olay_t.c.id)))
            vetolu = {(r.metin_id, r.enstruman) for r in b.execute(select(olay_t.c.metin_id, olay_t.c.enstruman).where(
                olay_t.c.tur == "veto", olay_t.c.rol.in_(roller)))}
            yukseltilmis = set(b.execute(select(jev_yargi.c.hedef).where(
                jev_yargi.c.rol.in_(roller), jev_yargi.c.saglayici == "nvidia", jev_yargi.c.hata.is_(None))).scalars())
        sayac = {"hazir": True, "yukseltildi": 0, "yeni_veto": 0, "korunan_veto": 0, "basarisiz": 0}
        for u in uyarilar:
            if (u.ayrinti or {}).get("yukseltme") is not None:
                continue
            hedef = f"metin:{u.metin_id}|{u.enstruman}"
            if hedef in yukseltilmis:
                continue
            rol = ROL_ADI[u.rol]
            with self.motor.connect() as b:
                m = b.execute(select(metin).where(metin.c.id == u.metin_id)).one()
            secim, model = self.yuk.sec(rol.ROL, hedef, rol.ETKI.model_dump(mode="json"), rol.hedef_state(m, u.enstruman),
                                        "etki")
            if secim is None:
                sayac["basarisiz"] += 1
                continue
            yukseltilmis.add(hedef)
            sayac["yukseltildi"] += 1
            if secim not in rol.VETO:
                sayac["korunan_veto"] += (u.metin_id, u.enstruman) in vetolu
                continue
            if (u.metin_id, u.enstruman) in vetolu:
                continue
            gecerli = simdi if (u.ayrinti or {}).get("canli") else u.gecerli_ms
            self._veto_yaz(rol, u.enstruman, gecerli, secim, f"yukseltme:{secim} ({model})", m, u.yargi_id,
                           {**(u.ayrinti or {}), "yukseltme": secim, "yukseltme_model": model, "sonradan": True})
            vetolu.add((u.metin_id, u.enstruman))
            sayac["yeni_veto"] += 1
        return sayac

    def son_metinler(self, kaynak: str, sinir: int | None = 200) -> list:
        """Kaynağın son `sinir` metni (yayın zamanına göre); yargısı olan (metin, enstrüman) çifti atlanır."""
        with self.motor.connect() as b:
            q = select(metin).where(metin.c.kaynak == kaynak).order_by(metin.c.yayin_ms.desc())
            return list(b.execute(q.limit(sinir) if sinir else q))

    def isle(self, kaynak: str, sinir: int | None = None) -> int:
        """Kaynağın metinlerini rolüyle değerlendirir (eskiden yeniye). Döndürür: yazılan olay sayısı."""
        rol = ROLLER[kaynak]
        evren = rol.evren(self.motor)
        simdi = int(time.time() * 1000)
        if sinir is not None:
            return sum(len(self.rol_metin(rol, m, evren, simdi)) for m in reversed(self.son_metinler(kaynak, sinir)))
        # Tümü (geçmiş doldurma, ~300 bin KAP metni): gövdeleriyle belleğe sığmaz → (yayın, id) sırasıyla parça parça.
        n, son = 0, (-1, -1)
        while True:
            with self.motor.connect() as b:
                parca = list(b.execute(select(metin).where(metin.c.kaynak == kaynak,
                                                           tuple_(metin.c.yayin_ms, metin.c.id) > son)
                                       .order_by(metin.c.yayin_ms, metin.c.id).limit(2000)))
            if not parca:
                return n
            n += sum(len(self.rol_metin(rol, m, evren, simdi)) for m in parca)
            son = (parca[-1].yayin_ms, parca[-1].id)

    def tur(self) -> dict:
        """Döndürür: yeni metin, olay sayısı ve `basarili` (toplaması ve yargılaması hatasız biten kaynaklar; nabız
        için, `zeka/nabiz.py`)."""
        yeni, olay_sayisi, basarili = 0, 0, set()
        for t in self.toplayicilar:
            try:
                yeni += len(t.canli(self.ayar))
                basarili.add(t.KAYNAK)
            except Exception as e:  # noqa: BLE001 — bir kaynak düşerse diğerleri sürer
                _log.error("toplayici_hatasi", kaynak=t.KAYNAK, hata=f"{type(e).__name__}: {e}"[:300])
        for t in self.toplayicilar:
            if t.KAYNAK not in ROLLER:  # rolü olmayan kaynak (RSS): yalnız toplanır, C özellikleri için birikir
                continue
            sinir = int(((self.ayar.get("tarama") or {}).get(t.KAYNAK)) or 200)
            try:
                olay_sayisi += self.isle(t.KAYNAK, sinir)
            except Exception as e:  # noqa: BLE001
                basarili.discard(t.KAYNAK)
                _log.error("isleme_hatasi", kaynak=t.KAYNAK, hata=f"{type(e).__name__}: {e}"[:300])
        return {"yeni_metin": yeni, "olay": olay_sayisi, "basarili": basarili}

    def jev_son(self, simdi_ms: int, pencere_ms: int = 6 * 3_600_000) -> tuple[int | None, int | None]:
        """Son başarılı ve son hatalı yargının zamanı (ms; `pencere_ms` içinde)."""
        from datetime import UTC, datetime

        bas = datetime.fromtimestamp((simdi_ms - pencere_ms) / 1000, UTC)
        with self.motor.connect() as b:
            iyi = b.execute(select(func.max(jev_yargi.c.zaman)).where(jev_yargi.c.zaman >= bas,
                                                                        jev_yargi.c.hata.is_(None))).scalar()
            kotu = b.execute(select(func.max(jev_yargi.c.zaman)).where(jev_yargi.c.zaman >= bas,
                                                                         jev_yargi.c.hata.is_not(None))).scalar()
        ms = lambda z: None if z is None else int((z if z.tzinfo else z.replace(tzinfo=UTC)).timestamp() * 1000)  # noqa: E731
        return ms(iyi), ms(kotu)


def toplayicilar(motor: Engine, a, ayar: dict) -> list:
    ham = HamDepo(a.veri_dizini, motor)
    from tradebot.metin.sec import Sec8K

    hepsi = {a1.KAYNAK: lambda: BinanceDuyuru(ham, motor), a2.KAYNAK: lambda: KapBildirim(ham, motor),
             a3.KAYNAK: lambda: Sec8K(ham, motor),
             "rss": lambda: RssToplayici(ham, motor, list(ayar.get("rss") or []))}
    return [hepsi[k]() for k in (ayar.get("kaynaklar") or list(hepsi))]


def kur(motor: Engine, a, ayar: dict | None = None) -> Zeka:
    """Ayarlar (sırlar) + config/zeka.yaml → çalışır servis. Anahtarlar yalnız ortamdan (kural 12)."""
    ayar = ayar or ayar_oku()
    jev = JevIstemci(motor, ayar["jev"]["model"],
                     api_key=a.typesafe_api_key.get_secret_value() if a.typesafe_api_key else None)
    y = ayar["yukseltme"]
    yuk = Yukseltme(motor, y["base_url"], list(y.get("modeller") or []),
                    a.nvidia_api_key.get_secret_value() if a.nvidia_api_key else None,
                    zaman_asimi=float(y.get("zaman_asimi_sn", 120)))
    return Zeka(motor, jev, yuk, toplayicilar(motor, a, ayar), ayar)
