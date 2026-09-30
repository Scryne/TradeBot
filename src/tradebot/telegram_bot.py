"""Telegram botu (Faz 9, D4): Scryne'ın doğal dil mesajı → Jev komut yönlendirmesi → kod cevaplar.

Kurallar (Araştırma §10.3 R3, kural 5/7/8):
- Yalnız `TRADEBOT_TELEGRAM_SOHBET`'ten gelen mesaja cevap verilir; diğerleri yok sayılır ve loglanır.
- Jev yalnız "ne isteniyor" sorusunu yargılar (komut + kol + kol netliği). Cevabı kod üretir; tahmin ve tavsiye yoktur.
- Okuma komutları: güven ≥ 0,5. Riski AZALTAN komutlar (kol/tümünü durdur): güven ≥ 0,7 + "evet" onayı (120 sn).
- Riski ARTIRAN hiçbir şey Jev'den geçmez: yalnız açık `/devam <kol>` + "evet" (kural 7). Jev bir mesajı
  `riski_artir` diye tanırsa bot yalnız bu yolu tarif eder.
- Kol belirsizse (ayrı Noul; spike: Jev tek kolu aşırı güvenle seçebiliyor) bot adayları listeler, onay mesajı hep
  kolun tam adını gösterir.
Spike: research/spikes/07_d4 (komut 12/12; netlik 6/8, hatalar güvenli yönde).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from typesafe_sdk import Choice, Noul

from tradebot.canli import dagitici as dg
from tradebot.canli.kollar import AGRESIF, PORTFOY, PaperKol
from tradebot.kayit import log

_log = log("telegram")
ONAY_SN = 120
OKUMA_ESIK, AZALTAN_ESIK = 0.5, 0.7
OKUMA = {"ozet", "kol_durumu", "dagitim", "vetolar", "rapor", "yardim"}
AZALTAN = {"kol_durdur", "tumunu_durdur"}

STRATEJI = {"ma_yon": "ma_yon (moving-average direction trend) arm", "tsmom": "tsmom (time-series momentum) arm",
            "donchian_ls": "donchian breakout arm", AGRESIF: "aggressive observation arm (full Kelly)",
            PORTFOY: "portfolio arm run by the capital allocator"}
ZD = {"1h": "1-hour bars", "4h": "4-hour bars", "1d": "daily bars"}

YARDIM = ("Sorabileceklerin: genel durum, bir kolun ya da tüm kolların durumu, dağıtım, aktif vetolar, son haftalık rapor.\n"
          "Riski azaltan: \"X kolunu durdur\", \"her şeyi durdur\" (onay ister).\n"
          "Riski artıran işler yalnız açık komutla: /devam <kol adı> (onay ister). Acil durdurma kaldırma yalnız host'ta CLI.\n"
          "Fiyat tahmini ya da işlem tavsiyesi vermem.")


def kol_aciklamasi(k: PaperKol) -> str:
    if k.strateji in (AGRESIF, PORTFOY):
        return STRATEJI[k.strateji]
    if k.strateji == "kilit_kisa":
        return ("token unlock arm: shorts a token's perpetual future 7 days before a large team/investor token unlock "
                "and hedges with a long BTC perpetual, daily decisions, without Jev veto")
    if k.strateji == "kanal_kirilim" and k.grup_adi == "xau_m15":
        return ("gold intraday scalping arm on the demo account: 15-minute channel breakout with ATR stop and 2R target, "
                "fixed 0.01 lot, real orders to the MT5 demo account, observation only")
    if k.strateji == "doviz_tasima":
        return ("forex carry arm on the demo account: long the highest-interest G10 currency and short the lowest, "
                "daily decisions, real orders to the MT5 demo account, observation only")
    dalga = "wave 2 (slow volatility estimate)" if k.ad.startswith("d2:") else "wave 1"
    return f"{STRATEJI.get(k.strateji, k.strateji)}, {ZD.get(k.zd, k.zd)}, BTC+ETH, {dalga}, " \
           f"{'with' if k.jev else 'without'} Jev veto"


def sorular(kollar: list[PaperKol]) -> dict:
    return {
        "komut": Choice(
            instructions={"what": "The message in `mesaj` is from the owner of an automated paper-trading system, sent to "
                                  "its Telegram bot. What is the owner asking the bot to do?",
                          "not_for": "The bot never predicts prices or gives trading advice, and never increases risk from "
                                     "a free-text message."},
            criteria={
                "ozet": "Show the overall status: whether the system is healthy and how the paper arms are doing in total.",
                "kol_durumu": "Show the performance, equity or positions of one arm or of all arms.",
                "dagitim": "Show the capital allocator's weekly allocation, weights or leverage.",
                "vetolar": "Show the currently active Jev vetoes or news/announcement blocks on instruments.",
                "rapor": "Show the latest weekly paper report.",
                "kol_durdur": "Stop one specific arm from taking new risk.",
                "tumunu_durdur": "Stop all arms / the whole system from taking new risk.",
                "riski_artir": "Resume, restart, un-stop or unfreeze something, lift a stop or veto, raise leverage, or "
                               "open/increase a position.",
                "yardim": "Ask what the bot can do or how to use it.",
                "bilinmiyor": {"what": "Anything else, including asking for price predictions, market direction or trading "
                                       "advice, or small talk."}}),
        "kol": Choice(instructions="Which paper-trading arm does the message in `mesaj` refer to? Use `kollar` for the "
                                   "arms' descriptions.",
                      criteria={**{k.ad: kol_aciklamasi(k) for k in kollar}, "hepsi": "All arms, or no specific arm is named."}),
        "net": Noul(instructions={"what": "Does the message in `mesaj` identify exactly one arm from `kollar` unambiguously, "
                                          "so that it could not also refer to another listed arm (for example the same "
                                          "strategy with and without Jev veto, or wave 1 and wave 2 of the same strategy)?",
                                  "not_for": "Do not assume a default when the message leaves the distinction open."}),
    }


@dataclass
class Bekleyen:
    eylem: str             # kol_durdur | tumunu_durdur | devam
    kollar: list[str]
    zaman: float = field(default_factory=time.monotonic)


class Bot:
    """Mesaj işleme (Telegram'dan bağımsız, test edilebilir). `sor(state, sorular) → {soru: cevap}` Jev çağrısıdır."""

    def __init__(self, motor, veri_dizini: Path, kollar: list[PaperKol], sor, simdi=time.time) -> None:
        self.m, self.veri, self.kollar, self.sor, self.simdi = motor, Path(veri_dizini), kollar, sor, simdi
        self.ad = {k.ad: k for k in kollar}
        self.bekleyen: Bekleyen | None = None

    # ------------------------------------------------------------------ giriş
    def isle(self, metin: str) -> str:
        metin = (metin or "").strip()
        if metin.lower() in ("evet", "/evet"):
            return self._onayla()
        if metin.lower().startswith("/devam"):
            kol = metin.split(maxsplit=1)[1].strip() if " " in metin else ""
            if kol not in self.ad:
                return "Kol adı tam yazılmalı. Kollar:\n" + "\n".join(f"• {k}" for k in self.ad)
            self.bekleyen = Bekleyen("devam", [kol])
            return (f"⚠️ RİSKİ ARTIRIR: {kol} kolunun durdurmasını kaldırayım mı? {ONAY_SN} sn içinde \"evet\" yaz.\n"
                    "(Acil durdurma bu yolla kalkmaz; o yalnız host'ta CLI ile.)")
        if metin.lower() in ("/start", "/yardim", "/help"):
            return YARDIM
        self.bekleyen = None
        c = self.sor({"mesaj": metin, "kollar": {k.ad: kol_aciklamasi(k) for k in self.kollar}}, sorular(self.kollar))
        if not c:
            return "Şu an mesajı yorumlayamadım (Jev'e ulaşılamadı). Host'ta `tradebot paper rapor` ya da bir süre sonra tekrar."
        komut, kg = c["komut"]["choice"], float(c["komut"]["confidence"] or 0)
        kol, kolg = c["kol"]["choice"], float(c["kol"]["confidence"] or 0)
        net = float(c["net"].get("noul") or 0)
        _log.info("telegram_komut", komut=komut, guven=round(kg, 2), kol=kol, kol_guven=round(kolg, 2), net=round(net, 2))
        if komut == "riski_artir":
            return ("Riski artıran işler serbest metinle yapılmaz (kural 7). Durdurulan bir kolu yeniden açmak için: "
                    "/devam <kol adı>. Acil durdurma kaldırma yalnız host'ta CLI ile. Kaldıraç/tavan değişikliği senin "
                    "açık kararınla, kodda yapılır.")
        if komut in AZALTAN:
            if kg < AZALTAN_ESIK:
                return f"Emin olamadım ({kg:.2f}). Ne durdurulsun: tek bir kol mu, hepsi mi? Kolun adını yazabilirsin."
            if komut == "tumunu_durdur":
                self.bekleyen = Bekleyen("tumunu_durdur", list(self.ad))
                return f"Bütün kollar yeni risk almayı durdursun mu ({len(self.ad)} kol)? {ONAY_SN} sn içinde \"evet\" yaz."
            adaylar = self._ikizler(kol) if kol in self.ad else list(self.ad)
            if kol not in self.ad or net < 0.5 or kolg < AZALTAN_ESIK:
                return "Hangi kol? Birini tam adıyla yaz:\n" + "\n".join(f"• {a}" for a in adaylar)
            self.bekleyen = Bekleyen("kol_durdur", [kol])
            return f"{kol} kolu yeni risk almayı durdursun mu? {ONAY_SN} sn içinde \"evet\" yaz."
        if komut in OKUMA and kg >= OKUMA_ESIK:
            try:
                return getattr(self, f"_{komut}")(kol if kol in self.ad else None)
            except Exception as e:  # noqa: BLE001
                _log.error("telegram_komut_hatasi", komut=komut, hata=f"{type(e).__name__}: {e}"[:200])
                return f"Cevabı hazırlarken hata oldu ({type(e).__name__}). Log'a yazıldı."
        return "Bunu yapamam ya da anlamadım.\n\n" + YARDIM

    def _ikizler(self, kol: str) -> list[str]:
        """Aynı stratejinin Jev'li/Jev'siz ve dalga 1/2 kopyaları (belirsizlikte listelenecek adaylar)."""
        k = self.ad[kol]
        return [a for a, x in self.ad.items() if x.strateji == k.strateji and x.zd == k.zd] or [kol]

    def _onayla(self) -> str:
        b, self.bekleyen = self.bekleyen, None
        if b is None or time.monotonic() - b.zaman > ONAY_SN:
            return "Onay bekleyen bir işlem yok (ya da süresi doldu)."
        from tradebot import denetim
        from tradebot.canli.defter import PaperDefter

        df = PaperDefter(self.m, "telegram")
        tur = "devam" if b.eylem == "devam" else "durdur"
        for k in b.kollar:
            df.kol_olay_yaz(k, tur, {"neden": "telegram", "eylem": b.eylem})
        denetim.kaydet(self.m, "telegram", f"kol_{tur}", {"kollar": b.kollar, "eylem": b.eylem})
        _log.warning("telegram_eylem", eylem=b.eylem, kollar=b.kollar)
        return (f"Tamam: {len(b.kollar)} kol için '{tur}' yazıldı. Paper düğümü bir sonraki saat kapanışında uygular "
                f"(durdurulan kol yalnız riski azaltan emir verir).")

    # ------------------------------------------------------------------ okuma komutları (kod cevaplar)
    def _isaretler(self) -> dict[str, list[tuple[int, float]]]:
        from tradebot.db import paper_ozkaynak

        bas = int(self.simdi() * 1000) - 2 * dg.GUN_MS
        out: dict[str, list] = {}
        with self.m.connect() as b:
            for r in b.execute(select(paper_ozkaynak.c.kol, paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak,
                                      paper_ozkaynak.c.pozisyon, paper_ozkaynak.c.fiyat)
                               .where(paper_ozkaynak.c.zaman_ms >= bas).order_by(paper_ozkaynak.c.zaman_ms)):
                out.setdefault(r.kol, []).append((int(r.zaman_ms), float(r.ozkaynak), r.pozisyon or {}, r.fiyat or {}))
        return out

    def _kol_satiri(self, ad: str, isaret: list) -> str:
        k = self.ad[ad]
        if not isaret:
            return f"• {ad}: işaret yok"
        simdi = isaret[-1]
        gun_once = [x for x in isaret if x[0] <= simdi[0] - dg.GUN_MS]
        g24 = (simdi[1] / gun_once[-1][1] - 1) if gun_once else None
        agirlik = ", ".join(f"{p.split(':')[-1].replace('USDT', '')} %{a * simdi[3].get(p, 0) / simdi[1] * 100:.0f}"
                            for p, a in simdi[2].items() if a) or "düz"
        return (f"• {ad}: {simdi[1]:,.0f} (başlangıçtan {simdi[1] / k.baslangic_ozkaynak - 1:+.2%}"
                f"{'' if g24 is None else f', 24 sa {g24:+.2%}'}) · {agirlik}")

    def _ozet(self, _kol) -> str:
        from tradebot import saglik
        from tradebot.ayar import ayarlar

        a = ayarlar()
        kontrol = [f(a) for f in (saglik.paper_kontrol, saglik.kilit_kontrol, saglik.gece_kontrol)] + \
                  ([saglik.yedek_kontrol(a)] if a.yedek_dizini else [])
        isaret = self._isaretler()
        ana = [k for k in self.ad if not k.endswith("+jev")]
        return ("Sağlık: " + " · ".join(f"{s.ad} {s.durum}" for s in kontrol) + "\n\nKollar (Jev'siz kopyalar, "
                "agresif, portföy):\n" + "\n".join(self._kol_satiri(k, isaret.get(k, [])) for k in ana))

    def _kol_durumu(self, kol) -> str:
        isaret = self._isaretler()
        adlar = [kol] if kol else list(self.ad)
        return "\n".join(self._kol_satiri(k, isaret.get(k, [])) for k in adlar)

    def _dagitim(self, _kol) -> str:
        from tradebot.db import paper_dagitim

        with self.m.connect() as b:
            r = b.execute(select(paper_dagitim).order_by(paper_dagitim.c.hafta_ms.desc()).limit(1)).first()
        if r is None:
            return "Henüz dağıtım kaydı yok."
        d = r.ayrinti
        satir = [f"• {k}: sınıf {v['sinif']}, gölge ağırlık {v.get('agirlik', 0):.2f}, katsayı {v['katsayi']:.2f}"
                 for k, v in d.get("kollar", {}).items()]
        return (f"Hafta {time.strftime('%Y-%m-%d', time.gmtime(r.hafta_ms / 1000))}: dağıtılan kaldıraç "
                f"{d.get('kaldirac', 0):.2f}x, gölge {d.get('kaldirac_golge', 0):.2f}x, uygun kol {len(d.get('uygun', []))}.\n"
                + "\n".join(satir) + ("\n(28 günlük paper geçmişi dolmadan gölge ağırlık hesaplanmaz.)"
                                      if not d.get("uygun") else ""))

    def _vetolar(self, _kol) -> str:
        from tradebot.zeka.olay import aktif_vetolar

        v = sorted(aktif_vetolar(self.m, int(self.simdi() * 1000)))
        paper = {x for k in self.kollar for x in k.grup["kimlikler"]}
        ilgili = [x for x in v if x in paper]
        return (f"Aktif veto: {len(v)} enstrüman. Paper kollarının enstrümanlarında: "
                f"{', '.join(ilgili) if ilgili else 'yok'}.\n" + (", ".join(v[:40]) + (" …" if len(v) > 40 else "")))

    def _rapor(self, _kol) -> str:
        from tradebot.canli import rapor

        yollar = sorted((self.veri / "rapor").glob("paper-*.md"))
        if not yollar:
            return "Henüz haftalık rapor yok (ilk rapor Pazartesi 00:30 UTC'den sonra)."
        from datetime import UTC, datetime

        h = int(datetime.strptime(yollar[-1].stem.removeprefix("paper-"), "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)
        return rapor.telegram_ozeti(rapor.ozetle(rapor.topla(self.m, dg.hafta_basi(h + dg.GUN_MS))))

    def _yardim(self, _kol) -> str:
        return YARDIM


class Telegram:
    def __init__(self, token: str) -> None:
        self.url = f"https://api.telegram.org/bot{token}/"

    def _cagir(self, yontem: str, veri: dict, zaman_asimi: float = 60) -> dict:
        govde = urllib.parse.urlencode(veri).encode()
        with urllib.request.urlopen(urllib.request.Request(self.url + yontem, data=govde), timeout=zaman_asimi) as r:
            return json.load(r)

    def guncellemeler(self, offset: int) -> list[dict]:
        return self._cagir("getUpdates", {"offset": offset, "timeout": 50, "allowed_updates": '["message"]'}, 65)["result"]

    def gonder(self, sohbet: str, metin: str) -> None:
        self._cagir("sendMessage", {"chat_id": sohbet, "text": metin[:4000], "disable_web_page_preview": "true"})


def ayri_dugum_kollari() -> list[PaperKol]:
    """Nautilus dışı düğümlerin kolları (kilit, MT5 demo kolları). "Hepsini durdur" bunları da kapsar (kural 7: riski
    azaltan her şey otomatik); 2026-09-30'a kadar yalnız kilit vardı, MT5 kolları dışarıda kalıyordu."""
    from tradebot.canli import akis, altin, doviz, kilit

    return [ay.kol for ay in (kilit.ayarlar(), doviz.ayarlar(), altin.ayarlar(), akis.ayarlar()) if ay is not None]


def calistir() -> None:
    """compose `telegram` servisi: uzun yoklama, yalnız Scryne'ın sohbeti."""
    from tradebot.ayar import ayarlar
    from tradebot.canli.kollar import kollar
    from tradebot.db import motor
    from tradebot.zeka.jev import JevIstemci
    from tradebot.zeka.servis import ayar_oku

    a = ayarlar()
    if a.telegram_token is None or not a.telegram_sohbet:
        raise RuntimeError("TRADEBOT_TELEGRAM_TOKEN ve TRADEBOT_TELEGRAM_SOHBET tanımlı olmalı")
    m = motor(a)
    jev = JevIstemci(m, ayar_oku()["jev"]["model"], api_key=a.typesafe_api_key.get_secret_value())

    def sor(state, s):
        y = jev.sor("D4_telegram", "telegram", state, s)
        return None if y.hata else y.cevap

    bot = Bot(m, a.veri_dizini, kollar() + ayri_dugum_kollari(), sor)
    tg = Telegram(a.telegram_token.get_secret_value())
    offset = 0
    _log.info("telegram_basladi")
    while True:
        try:
            for u in tg.guncellemeler(offset):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                sohbet = str((msg.get("chat") or {}).get("id"))
                if sohbet != str(a.telegram_sohbet):
                    _log.warning("telegram_yabanci_sohbet", sohbet=sohbet)
                    continue
                tg.gonder(sohbet, bot.isle(msg.get("text") or ""))
        except Exception as e:  # noqa: BLE001 — ağ hatası servisi durdurmaz
            _log.warning("telegram_dongu_hatasi", hata=f"{type(e).__name__}: {e}"[:200])
            time.sleep(5)

