---
version: alpha
name: TradeBot
description: Scryne'ın otonom paper trade sisteminin özel kontrol panosu; tek kullanıcı, masaüstü ve telefon, yalnız Tailscale.
colors:
  gece: "#0B0D1A"
  yuzey: "#12152A"
  yuzey-ust: "#1A1E38"
  cizgi: "#2A2F52"
  mesh-indigo: "#262A6B"
  mesh-petrol: "#0C4A55"
  mesh-murdum: "#4A1D44"
  sis: "#E8ECF6"
  kursun: "#9AA3BD"
  soluk: "#7D86A6"
  sodyum: "#F2B35B"
  sodyum-koyu: "#3A2A12"
  kazanc: "#5ED3A6"
  kayip: "#FF7F73"
typography:
  display-xl:
    fontFamily: Big Shoulders
    fontSize: 64px
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: -0.01em
  display-md:
    fontFamily: Big Shoulders
    fontSize: 32px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0.01em
  body-md:
    fontFamily: Onest
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: Onest
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
  data-lg:
    fontFamily: Azeret Mono
    fontSize: 22px
    fontWeight: 500
    lineHeight: 1.1
    fontFeature: '"tnum" 1, "zero" 1'
  data-md:
    fontFamily: Azeret Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
    fontFeature: '"tnum" 1, "zero" 1'
  label-sm:
    fontFamily: Azeret Mono
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0.12em
rounded:
  control: 8px
  panel: 14px
  full: 9999px
spacing:
  gutter: 16px
  panel: 20px
  section: 72px
components:
  ust-cubuk:
    backgroundColor: "rgba(18, 21, 42, 0.55)"
    textColor: "{colors.sis}"
    height: 56px
  panel:
    backgroundColor: "{colors.yuzey}"
    textColor: "{colors.sis}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  cam-panel:
    backgroundColor: "rgba(255, 255, 255, 0.06)"
    textColor: "{colors.sis}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  etiket:
    backgroundColor: "{colors.yuzey-ust}"
    textColor: "{colors.kursun}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
  etiket-dikkat:
    backgroundColor: "{colors.sodyum-koyu}"
    textColor: "{colors.sodyum}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
  serit-hucre:
    backgroundColor: "{colors.sis}"
    size: 10px
---

# TradeBot

## Overview

Pano, TradeBot'un gece de çalışan bir ölçüm aletidir: sakin, kesin, abartısız. Beş saniyede üç soruya cevap verir:
sistem sağlıklı mı, son kararlar ne, kollar nasıl gidiyor. Kumarhane ekranı değildir: yanıp sönen mum grafiği, neon
yeşil/kırmızı ve "kazan" dili yok. Sistem her kararı emirden önce kaydeder, ön kayıt yapar, zinciri hash'ler; pano da
bu disiplini gösterir: her sayı bir kaynaktan gelir, her zaman damgası UTC ile birlikte yerel saati de verir.

Taban disiplin global dark glassmorphism'dir. Bu dosya onun üstüne projeye özgü katmanı koyar: Haliç gecesi paleti,
tabela kökenli dar display yazı ve imza öğe olarak **karar şeridi**.

Pano yalnız koyu temadır. Tek kullanıcı, çoğunlukla gece ve telefondan bakıyor. Açık tema yok; `prefers-color-scheme`
açık olsa da aynı koyu görünüm verilir.

## Colors

- Arka plan düz `gece` değildir. Üç derin leke (`mesh-indigo` sol üst, `mesh-petrol` sağ orta, `mesh-murdum` sol alt)
  sabit bir mesh kurar. Işık sol üstten gelir, sağ alt en koyudur. Mesh hareket etmez.
- `sodyum` tek marka aksanıdır ve "şimdi / dikkat" anlamı taşır: şeritteki şimdi çizgisi, aktif sekme, odak halkası, Jev
  vetosu. Başka hiçbir öğe sodyum renkte olmaz; dekorasyon için kullanılmaz.
- `kazanc` ve `kayip` yalnız işaretli sayılar ve getiri çizgileri içindir. Hiçbir zaman tek başına anlam taşımaz: her
  işaretli sayıda `+` / `−` işareti de yazılır.
- Fren ve acil durdurma `kayip` ile, veto `sodyum` ile gösterilir. Maruziyet (pozisyon büyüklüğü) iyi ya da kötü
  değildir: `sis`in saydamlık rampasıyla çizilir, renkle değil.
- Metin hiyerarşisi üç adımdır: `sis` (birincil), `kursun` (ikincil), `soluk` (üçüncül: tablo başlığı, eksen, ikiz
  satır). Üçü de en koyu yüzey olan `yuzey-ust` üzerinde 4,5:1'i geçer; yeni bir metin rengi bu çıtanın altına inmez.
  Kenarlar `cizgi` renginde 1 px'tir.

## Typography

- **Big Shoulders** (dar, tabela kökenli; kalkış panosu, gösterge levhası) yalnız iki yerde: kahraman durum cümlesi
  (`display-xl`) ve bölüm başlıkları (`display-md`). Gövde metninde, butonda, tabloda kullanılmaz. Masaüstünde
  `display-xl` 88 px'e kadar büyür; telefonda 44 px'e iner.
- **Onest** bütün arayüz metnidir: açıklama, veto gerekçesi, sağlık ayrıntısı.
- **Azeret Mono** her sayının, saatin, hash'in ve kol adının yazısıdır. Rakamlar tabular ve sıfır çizgilidir, sütunlar
  hizalı durur. `label-sm` büyük harf, geniş aralıklı üst etikettir (bölüm içi alt başlık, tablo başlığı).
- Sayı biçimi Türkçedir: binlik nokta, ondalık virgül (`1.199.332`, `−%0,06`). Eksi işareti U+2212'dir.

## Layout

- Tek sayfa, yukarıdan aşağı okunur. Sıra önem sırasıdır: durum cümlesi ve karar şeridi, kollar, pozisyon ve risk,
  Jev ve veto, araştırma defteri, sağlık. Kol ayrıntısı sağdan açılan bir çekmecede görünür, sayfa değişmez.
- Bölümler aynı kalıbı tekrarlamaz: kahraman tam genişlik, şerit kenardan kenara bant, kollar yoğun liste, risk ve veto
  7/5 asimetrik bölünme, defter liste, sağlık sıkı ızgara.
- İçerik genişliği en çok 1320 px; kenar boşluğu `gutter`. Bölümler arası `section`, panel içi `panel`.
- Telefonda (390 px) her şey tek sütundur. Karar şeridi kendi kutusunda yatay kayar, kol adları solda sabit kalır;
  sayfa asla yatay kaymaz.

## Elevation & Depth

- Cam (`backdrop-filter: blur(12px)`) yalnız üç yüzeyde: üst çubuk, kahraman durum paneli ve kol çekmecesi. Diğer
  paneller düz `yuzey` renktedir; blur yığılmaz.
- Derinlik gölgeyle değil katmanla verilir: `gece` → `yuzey` → `yuzey-ust`, aralarında 1 px `cizgi`. Gölge yalnız
  çekmecede.
- `backdrop-filter` desteklenmezse cam yüzeyler opak `yuzey` olur.

## Shapes

- Paneller `panel`, kontroller `control`, etiketler `full` yarıçaplıdır. Karar şeridi hücreleri kare köşelidir:
  şerit bir ölçüm kaydıdır, dekoratif değildir.

## Components

- **Karar şeridi (imza):** satırlar kollar, sütunlar son 72 saatin saatleri. Hücre dolgusu o saatteki brüt maruziyettir
  (`sis`, saydamlık 0,06 → 0,9). Veto olan saatin üstünde `sodyum` bir çentik, frenli kararın altında `kayip` bir çizgi
  vardır. Sağ kenarda `sodyum` şimdi çizgisi. Hücreye dokunmak ya da üzerine gelmek o kararın ayrıntısını gösterir.
- **Kol satırı:** kol adı, Jev'li ve Jev'siz kopyanın ikiz getiri çizgisi (aralarındaki alan hangisi öndeyse onun
  rengiyle, düşük opaklıkta), toplam getiri, en kötü düşüş, işlem sayısı, yürütme maliyeti. Satır çekmeceyi açar.
- **Etiket:** durum bildirir (`normal`, `fren`, `veto`, `KALDI`, `açık`). Rengin yanında her zaman metin vardır.
- İkonlar Lucide, 16 px, `currentColor`. Emoji yok.

## Do's and Don'ts

- Don't: panoya hiçbir emir, durdurma, yeniden başlatma ya da ayar kontrolü koyma. Pano salt okunurdur.
- Don't: sır, anahtar, hesap numarası ya da parola gösterme.
- Do: her zaman damgasını UTC ve İstanbul saatiyle birlikte yaz; veri bayatsa (son işaret 2 saatten eskiyse) bunu açıkça
  söyle.
- Don't: `sodyum`u dekorasyon için kullanma.
- Don't: hareketli arka plan, sürekli animasyon ya da animasyonlu blur.
