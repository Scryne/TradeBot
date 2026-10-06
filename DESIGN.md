---
version: alpha
name: TradeBot · Nothing denemesi
description: TradeBot panosunun monokrom, tipografik, endüstriyel deneme varyantı (dal deneme/nothing-pano); tek kullanıcı, masaüstü ve telefon, yalnız Tailscale.
colors:
  siyah: "#000000"
  yuzey: "#111111"
  yuzey-ust: "#1A1A1A"
  cizgi: "#222222"
  cizgi-belirgin: "#333333"
  pasif: "#666666"
  ucuncul: "#858585"
  ikincil: "#999999"
  birincil: "#E8E8E8"
  ekran: "#FFFFFF"
  kirmizi: "#D71921"
  kirmizi-metin: "#FF4D55"
  yesil: "#4A9E5C"
  amber: "#D4A843"
typography:
  hero:
    fontFamily: Doto
    fontSize: 120px
    fontWeight: 700
    lineHeight: 0.9
    letterSpacing: -0.02em
  baslik:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: -0.01em
  govde:
    fontFamily: Space Grotesk
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.5
  govde-sm:
    fontFamily: Space Grotesk
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
  veri-lg:
    fontFamily: Space Mono
    fontSize: 24px
    fontWeight: 400
    lineHeight: 1.1
  veri:
    fontFamily: Space Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
  etiket:
    fontFamily: Space Mono
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: 0.08em
rounded:
  teknik: 4px
  kart: 12px
  hap: 999px
spacing:
  gutter: 16px
  panel: 24px
  bolum: 96px
components:
  ust-cubuk:
    backgroundColor: "{colors.siyah}"
    textColor: "{colors.birincil}"
    height: 56px
  kart:
    backgroundColor: "{colors.yuzey}"
    textColor: "{colors.birincil}"
    rounded: "{rounded.kart}"
    padding: "{spacing.panel}"
  durum-etiketi:
    backgroundColor: "transparent"
    textColor: "{colors.ikincil}"
    typography: "{typography.etiket}"
    rounded: "{rounded.hap}"
  segment:
    backgroundColor: "{colors.ekran}"
    rounded: "0px"
---

# TradeBot · Nothing denemesi

> **Deneme dalı.** Bu dosya yalnız `deneme/nothing-pano` dalında geçerli; `main`'deki Haliç gecesi `DESIGN.md`'si
> yerinde. Varyant `pano/nothing.html`'de, karşılaştırma için eski pano aynı dalda `/` adresinde duruyor. Kaynak
> stil: `nothing-design` skill'i (yerel geçersiz kılmalarıyla).

## Overview

Pano bir ölçüm aletidir: karanlık odada bir enstrüman paneli, beyaz veriler siyahın üstünde parlıyor. Beş saniyede üç
soruya cevap verir: sistem sağlıklı mı, son kararlar ne, kollar nasıl gidiyor. Süs yoktur: gradient, cam, gölge, blur
yok. Hiyerarşiyi boyut, boşluk ve gri tonları kurar; renk bir olaydır.

Değişmeyen içerik kuralları (main'deki DESIGN.md'den aynen): pano salt okunurdur; sır gösterilmez; her zaman damgası
İstanbul ve UTC birlikte yazılır; veri 2 saatten bayatsa bu açıkça söylenir; sayı biçimi Türkçedir (binlik nokta,
ondalık virgül, eksi U+2212). Yalnız koyu tema.

## Colors

- Arka plan düz `siyah` (OLED). Yüzeyler `yuzey` → `yuzey-ust`, aralarında 1 px `cizgi`. Derinlik katmanla verilir.
- Metin dört gri adımdır: `ekran` (kahraman sayı, ekranda bir tane), `birincil` (gövde), `ikincil` (etiket, açıklama),
  `ucuncul` (tablo başlığı, zaman damgası). `ucuncul` upstream'deki `#666` yerine `#858585`'tir: `yuzey-ust`
  üstünde 4,7:1. `pasif` (`#666`) yalnız devre dışı öğede ve süste kullanılır, okunacak metne verilmez.
- Durum renkleri yalnız değere uygulanır, etikete ya da satır arka planına değil: kazanç `yesil`, kayıp ve fren
  `kirmizi`, Jev vetosu `amber`. Metin olarak kırmızı `kirmizi-metin`'dir (`#D71921` küçük metinde 4,05:1, AA'yı
  geçmez); dolgu, çizgi ve nokta `kirmizi`. Her işaretli sayıda `+` / `−` de yazılır, renk tek başına anlam taşımaz.
- Kırmızı bir kesintidir: acil bir şey yoksa ekranda kırmızı dolgu yoktur. "Şimdi" çizgisi ve odak halkası `ekran`.
- Maruziyet iyi ya da kötü değildir: `ekran`ın saydamlık rampasıyla ya da segment sayısıyla çizilir.

## Typography

- **Doto** (nokta matris) yalnız kahraman sayıda: ekran başına bir kez, 72 px'ten büyük.
- **Space Grotesk** başlık ve gövde. **Space Mono** her sayı, saat, hash ve etiket. Etiketler BÜYÜK HARF, 11 px,
  0,08em aralık; `lang="tr"` olduğu için `i` → `İ` doğru büyür.
- Bütçe: Doto hariç üç ana boyut (24 / 15 / 11; 13 yalnız tablo ve ikincil gövde). Ağırlık 400; 700 yalnız Doto'da.
  Kalın gövde metni yok.

## Layout

- Tek sayfa, önem sırasıyla: kahraman + karar şeridi, kollar, risk ve Jev (7/5), araştırma defteri, sağlık.
- Asimetri: kahramanda büyük sol (sayı + cümle), dar sağ (turnuva cetveli + 24 saat sayaçları).
- Gruplama önce boşlukla: bölüm arası 96 px, grup arası 32–48 px, öğe arası 16 px. Ayırıcı çizgi yalnız yapısal olarak
  aynı satırların olduğu listelerde. Kahraman kutulanmaz, siyahın üstünde durur.
- Telefonda (390 px) tek sütun; karar şeridi kendi kutusunda yatay kayar, sayfa asla kaymaz.

## Elevation & Depth

Gölge yok, blur yok. Kol çekmecesi `yuzey` + 1 px `cizgi-belirgin`; arkası `siyah` %80.

## Shapes

Kartlar 12 px, teknik öğeler 4 px, etiket ve buton hap. Segmentler ve şerit noktaları köşesizdir/yuvarlaktır, süs değil
ölçümdür.

## Components

- **Segmentli çubuk (imza):** ayrık bloklar, 2 px aralık. Turnuva cetveli 84 gün = 84 segment; maruziyet 10 segment;
  pozisyon merkezden iki yana 12'şer segment, 10. segment tavandır, tavanı aşan segmentler `kirmizi`. Çubuğun yanında
  her zaman sayı yazar: çubuk oran, sayı kesinlik.
- **Karar şeridi:** satırlar kollar, sütunlar son 72 saat; her hücre bir nokta, noktanın saydamlığı brüt maruziyet.
  Dolum noktası büyür, veto üstte `amber` çentik, fren altta `kirmizi` çizgi, sağ kenarda `ekran` şimdi çizgisi.
- **Durum etiketi:** köşeli parantezli metin: `[NORMAL]`, `[GÜNLÜK FREN]`, `[VETO]`. Bildirim balonu (toast) yok.
- **Yükleniyor:** `[YÜKLENİYOR]` metni; iskelet ekran yok. **Hata:** `[HATA]` önekli satır içi metin, kırmızı arka
  plan yok.
- İkonlar Lucide, ince çizgi, 16 px; dolgulu ikon ve emoji yok.

## Do's and Don'ts

- Don't: gradient, gölge, blur, yaylanan animasyon, zebra satır.
- Don't: panoya emir, durdurma ya da ayar kontrolü koyma; sır gösterme.
- Do: ekran başına tek kırılma (kahraman Doto sayısı); geri kalanı sakin ve tutarlı.
- Do: hareket yalnız opaklık, 150–250 ms ease-out.
