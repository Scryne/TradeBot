"""Spike 04-B: Jev ile KAP bildirimi sınıflandırma (rol A2 koruma + B1 kurumsal işlem tespiti), Türkçe.

Soru: bu bildirim `sembol` payını tutan birini nasıl etkiliyor? Etiketler Claude'un metni okuyarak verdiği altın
cevaplardır; tartışmalı olanlarda kabul kümesi geniştir. Tuzaklar: "Temerrüt İşlemi" (yatırımcı takas temerrüdü,
şirket değil), bağlı ortaklık sermaye artırımı (ana payı düzeltmez), toplu SPK işlem yasağı listeleri.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from typesafe_sdk import Choice, Score, TypeSafeClient

MODEL = "jev-1.13.0"
D = Path(__file__).parent / "data"
VETO = {"pazar_tedbiri", "olumsuz_esasli"}

ETKI = Choice(
    instructions={
        "what": "Bu KAP bildiriminin, Borsa İstanbul'da `sembol` kodlu şirketin payını elinde tutan bir yatırımcı için "
                "anlamını sınıflandır. `bildirim.baslik` ve `bildirim.metin` alanlarını oku. Yalnız `sembol` şirketinin "
                "kendi payı açısından değerlendir; bildirimde geçen başka şirketleri, bağlı ortaklıkları ya da yatırımcıları "
                "`sembol` ile karıştırma.",
        "not_for": "Fiyatın ne yöne gideceğini tahmin etme; yalnız bildirimin ne söylediğini değerlendir.",
    },
    criteria={
        "pazar_tedbiri": {
            "what": "Borsa İstanbul ya da SPK, `sembol` payının kendisine tedbir uyguluyor: Yakın İzleme Pazarı'na alma, "
                    "brüt takas, kredili işlem veya açığa satış yasağı, tek fiyat yöntemi, işlem sırasının kapatılması ya da kottan çıkarma.",
            "not_for": "Belirli kişilere yönelik SPK işlem yasağı listeleri, devre kesici, yatırımcıların takas temerrüdü."},
        "gecici_durdurma": {
            "what": "`sembol` payında sürekli işleme kısa süreli ara verildi (devre kesici, tek fiyat emir toplama) ve işlemler aynı gün devam ediyor."},
        "kurumsal_islem": {
            "what": "`sembol` şirketinin KENDİ payını etkileyen sermaye olayı: bedelsiz, bedelli ya da tahsisli sermaye artırımı, "
                    "sermaye azaltımı, pay bölünmesi, kâr payı (temettü) dağıtımı, hak kullanımı. Fiyat serisinde düzeltme gerektirebilir.",
            "not_for": "Bağlı ortaklığın ya da iştirakin sermaye artırımı; `sembol` payının sayısını değiştirmeyen işlemler."},
        "olumsuz_esasli": {
            "what": "Şirketin kendisi için esaslı olumsuz gelişme: finansal zorluk, borç temerrüdü, iflas/konkordato, dava ya da idari ceza, "
                    "üretimin durması, önemli bir projenin iptali ya da ertelenmesi, endeksten çıkarılma.",
            "not_for": "Borsa'nın bir yatırımcının takas yükümlülüğü için yaptığı 'Temerrüt İşlemi' duyurusu; rutin bildirimler."},
        "olumlu_esasli": {
            "what": "Şirket için esaslı olumlu gelişme: yeni sözleşme, ihale kazanma, yatırım, kapasite artışı, pay geri alımı, "
                    "varlık edinimi, kredi notunun yükseltilmesi."},
        "rutin": {
            "what": "Olağan bilgilendirme: finansal rapor yayımı, trafik/operasyon verileri, notun teyidi, kupon ödemesi, bilgi formları, "
                    "ortakların pay alım satım bildirimleri, payların borsada işlem gören tipe dönüşümü, yatırımcı takas temerrüdü işlemleri, "
                    "kişilere yönelik toplu SPK işlem yasağı listeleri, bağlı ortaklıkların rutin finansman işlemleri."},
    },
)

ACILIYET = Score(
    instructions="`sembol` payını tutan bir yatırımcı bu bildirim yüzünden ne kadar acil davranmalı?",
    criteria=[
        "Hiçbir şey yapmasına gerek yok: rutin ya da ilgisiz bilgi.",
        "Bilgi amaçlı: not edilmeli ama pozisyonu etkilemez.",
        "Dikkat: fiyat serisini ya da pozisyon büyüklüğünü etkileyebilecek bir olay (sermaye işlemi, geçici durdurma, önemli haber).",
        "Harekete geç: pay üzerinde tedbir, ciddi finansal sıkıntı ya da işlem koşullarını değiştiren bir karar var.",
        "Hemen harekete geç: işlem yasağı, kottan çıkma, iflas ya da benzeri ağır durum.",
    ],
)

# (bildirim indeksi, altın etiket, kabul kümesi)
ETIKET = {
    0: ("rutin", None), 1: ("gecici_durdurma", None), 2: ("rutin", None), 3: ("rutin", None),
    4: ("kurumsal_islem", {"kurumsal_islem", "rutin"}), 5: ("rutin", {"rutin", "olumlu_esasli"}),
    6: ("olumlu_esasli", None), 7: ("rutin", None), 8: ("gecici_durdurma", None),
    9: ("rutin", {"rutin", "olumlu_esasli"}), 10: ("rutin", {"rutin", "olumlu_esasli"}),
    11: ("olumsuz_esasli", {"olumsuz_esasli", "rutin"}), 12: ("rutin", None), 13: ("rutin", None),
    14: ("gecici_durdurma", None), 15: ("olumlu_esasli", {"olumlu_esasli", "rutin"}), 16: ("rutin", None),
    17: ("olumlu_esasli", None), 18: ("olumlu_esasli", {"olumlu_esasli", "rutin"}), 19: ("rutin", None),
    20: ("rutin", None), 21: ("rutin", None), 22: ("kurumsal_islem", None), 23: ("olumsuz_esasli", None),
    24: ("olumlu_esasli", None), 25: ("rutin", {"rutin", "olumlu_esasli"}), 26: ("rutin", None),
    27: ("kurumsal_islem", None), 28: ("rutin", None), 29: ("rutin", None),
    30: ("olumlu_esasli", {"olumlu_esasli", "rutin"}), 31: ("rutin", None), 32: ("rutin", {"rutin", "olumlu_esasli"}),
    33: ("kurumsal_islem", {"kurumsal_islem", "rutin", "olumsuz_esasli"}), 34: ("rutin", None), 35: ("rutin", None),
    36: ("olumlu_esasli", {"olumlu_esasli", "rutin"}), 37: ("olumlu_esasli", {"olumlu_esasli", "rutin"}),
    38: ("olumlu_esasli", None), 39: ("kurumsal_islem", {"kurumsal_islem", "rutin"}), 40: ("pazar_tedbiri", None),
    41: ("olumlu_esasli", {"olumlu_esasli", "rutin"}), 42: ("kurumsal_islem", {"kurumsal_islem", "rutin"}),
    43: ("olumsuz_esasli", {"olumsuz_esasli", "rutin", "pazar_tedbiri"}),
}
TUZAK = {3: "temerrüt (yatırımcı)", 7: "temerrüt (yatırımcı)", 26: "temerrüt (yatırımcı)",
         10: "bağlı ortaklık SA", 32: "bağlı ortaklık SA", 2: "toplu SPK yasağı listesi", 12: "toplu SPK yasağı listesi"}
KELIMELER = ("temerrüt", "yasağı", "tedbir", "iflas", "konkordato", "zorluk", "yakın izleme", "devre kesici")


def main() -> None:
    sec = json.load(open(D / "kap_secki.json", encoding="utf-8"))
    istemci = TypeSafeClient()
    kayit, sureler = [], []
    for i, (altin, kabul) in ETIKET.items():
        kabul = kabul or {altin}
        b = sec[i]
        state = {"sembol": b["sembol"], "bildirim": {"baslik": b["baslik"], "metin": b["govde"][:4000]}}
        t0 = time.perf_counter()
        r = istemci.system_one(state, {"etki": ETKI, "aciliyet": ACILIYET}, model=MODEL)
        sureler.append(time.perf_counter() - t0)
        c, s = r.choices["etki"], r.scores["aciliyet"]
        m = (b["baslik"] + " " + b["govde"]).lower()
        kayit.append({"i": i, "sembol": b["sembol"], "baslik": b["baslik"], "altin": altin, "kabul": sorted(kabul),
                      "jev": c.choice, "guven": round(c.confidence, 3), "aciliyet": round(s.score, 2),
                      "dogru": c.choice in kabul, "veto_altin": altin in VETO, "veto_jev": c.choice in VETO,
                      "veto_kelime": any(k in m for k in KELIMELER), "girdi_token": r.usage.input_tokens})
        k = kayit[-1]
        print(f"{'✓' if k['dogru'] else '✗'} #{i:<2} {b['sembol']:<6} altın={altin:<16} jev={c.choice:<16} güven={c.confidence:.2f} "
              f"aciliyet={s.score:.2f} {('← TUZAK: ' + TUZAK[i]) if i in TUZAK else ''}")
    json.dump({"model": MODEL, "kayit": kayit}, open(D / "veto_kap_sonuc.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n, dogru = len(kayit), sum(k["dogru"] for k in kayit)
    print(f"\nETKİ doğruluğu: {dogru}/{n} = %{dogru / n * 100:.0f}  · tuzaklar: "
          f"{sum(k['dogru'] for k in kayit if k['i'] in TUZAK)}/{len(TUZAK)}")
    for ad, a in (("Jev", "veto_jev"), ("Anahtar kelime", "veto_kelime")):
        tp = sum(k[a] and k["veto_altin"] for k in kayit); fp = sum(k[a] and not k["veto_altin"] for k in kayit)
        fn = sum((not k[a]) and k["veto_altin"] for k in kayit)
        print(f"{ad:<15} VETO — doğru {tp}, yanlış alarm {fp}, KAÇIRILAN {fn} (gerçek {tp + fn})")
    ki = [k for k in kayit if k["jev"] == "kurumsal_islem"]
    print(f"B1 kurumsal işlem: Jev {len(ki)} işaretledi, doğru {sum(k['altin'] == 'kurumsal_islem' or 'kurumsal_islem' in k['kabul'] for k in ki)}")
    for esik in (0.5, 0.7, 0.9):
        alt = [k for k in kayit if k["guven"] >= esik]
        print(f"güven ≥ {esik}: {len(alt)}/{n}, doğruluk %{sum(k['dogru'] for k in alt) / max(len(alt), 1) * 100:.0f}")
    print("\nYanlışlar:")
    for k in kayit:
        if not k["dogru"]:
            print(f"  #{k['i']} {k['sembol']} {k['baslik'][:50]}: altın {k['altin']} ← jev {k['jev']} (güven {k['guven']})")
    print(f"\ngecikme medyan {statistics.median(sureler):.2f} sn · ortalama girdi {statistics.mean(k['girdi_token'] or 0 for k in kayit):.0f} token")


if __name__ == "__main__":
    main()
