# ruff: noqa: E501  (soru tanımları Spike 04-A ile birebir; satır bölmek metni ve SORU_SHA'yı değiştirir)
"""Rol A2: KAP bildirimi → BIST payı için veto (Spike 04-A: 44/44 doğru, yanlış veto 0; tuzaklar 7/7).

Soru: bu bildirim `sembol` payını tutan birini nasıl etkiliyor? (Choice `etki` + Score `aciliyet`.) Türkçe.
Karar yalnız Choice'a dayanır; Score alarm önceliği içindir. Karar kuralı A1 ile aynı (`zeka.karar.karar`).
Veto süreli: `pazar_tedbiri` ve `olumsuz_esasli` kalıcı değil (KAP'ta tedbirin kalkışı ayrı bir bildirimdir; olumsuz
gelişme kalıcı delist değildir). Süreler `config/zeka.yaml` `kap.veto_gun`'de.
`kurumsal_islem` (B1) veto değil, `kurumsal` olayı: veri hattının Yahoo bölünme/bedelsiz düzeltmesiyle çapraz kontrolü için.
Soru tanımları Spike 04-A'nın birebir kopyasıdır; `SORU_SHA` testi değişikliği yakalar.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine
from typesafe_sdk import Choice, Score

from tradebot.db import enstruman

ROL = "A2_kap"
KAYNAK = "kap"
ONEK = "A2"
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

SORULAR = {"etki": ETKI, "aciliyet": ACILIYET}
AZAMI_ADAY = 20


def evren(motor: Engine) -> set[str]:
    with motor.connect() as b:
        return set(b.execute(select(enstruman.c.kimlik).where(enstruman.c.piyasa == "BIST",
                                                              enstruman.c.sinif == "hisse")).scalars())


def hedefler(m, evren_: set[str]) -> list[str]:
    """Bildirimin hisse kodlarından evrende olanlar. Atlanan konular (`metin.kap.ATLA`) hiç sorulmaz."""
    meta = m.meta or {}
    if meta.get("atla"):
        return []
    return [f"BIST:{k}" for k in meta.get("kodlar", []) if f"BIST:{k}" in evren_][:AZAMI_ADAY]


def hedef_state(m, kimlik: str) -> dict:
    return {"sembol": kimlik.removeprefix("BIST:"), "bildirim": {"baslik": m.baslik, "metin": m.govde[:4000]}}


def veto_suresi_ms(secim: str | None, ayar: dict) -> int | None:
    gun = ((ayar.get("kap") or {}).get("veto_gun") or {}).get(secim)
    return int(gun) * 86_400_000 if gun else None


def bilgi_olayi(secim: str | None) -> str | None:
    """Veto dışı ama kayda değer seçim → olay türü."""
    return "kurumsal" if secim == "kurumsal_islem" else None
