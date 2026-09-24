# TradeBot

Bu proje Scryne'ın Proje Çalışma Akışı'nı takip eder (bkz. global `~/.claude/CLAUDE.md`, ve
detaylı gerekçeler için ScryneOS vault'unda `🧠 500-Knowledge/Proje-Calisma-Akisi.md`).

## Durum

Şu anki aşama `.claude/state.json` içinde tutulur, `session-start` hook'u her oturum başında
bunu okuyup bağlama enjekte eder — nerede kaldığımızı sormana gerek kalmaz. Bir aşama
bittiğinde `asama` alanını sırayla güncelle: `fikir` → `denetim` → `finalizasyon` → `roadmap`
→ `uygulama` → `tamamlandi`. Aynı anda ScryneOS vault'undaki
`🏰 300-Projects/TradeBot.md` index notunu da güncelle (frontmatter `asama`/`modified` +
`**Aşama:**` satırı — vault oturumu bunu okuyarak projeyi bilir).

Hook'lar (`.claude/hooks/`) `proje-baslat` şablonunun birebir kopyasıdır; burada elle
değiştirilmez. Kanonik roadmap `docs/Roadmap.md` dışında bir dosyaysa `state.json`'a
`"roadmap": "docs/<dosya>.md"` yazılır, iki hook da onu okur.

## Dosyalar

- `docs/Proje-Fikri.md` — ilk fikir
- `docs/Final-Dokuman.md` — nihai kararlar (teknoloji stack, mimari, riskler)
- `docs/Roadmap.md` — fazlı yol haritası; her faz "Durum" sütunuyla takip edilir, hook bunu
  otomatik okur
- `DESIGN.md` (proje kökünde) — bu projeye özel frontend kimliği. Kesin değerler
  frontmatter'da, gerekçe Markdown'da.

## Frontend

Taban disiplin ve araç sırası global `~/.claude/CLAUDE.md`'de (burada tekrarlanmaz). Projeye
özel karakteri kökteki `DESIGN.md` belirler ve çelişkide global varsayılanı ezer.

---

## TradeBot'a özel — değişmez kurallar

Bu proje gerçek parayla temas edecek. Aşağıdakiler tercih değil, kısıttır. Gerekçeler `docs/Arastirma.md`.

1. **Sıfırdan.** ScryneQuant projesine bakılmaz. Kararları, kodu ve ölçümleri taşınmaz (Scryne, 2026-09-24).
2. **Backtest = canlı.** Karar fonksiyonu tektir. Karar kapanmış barla verilir, dolum sonraki barın
   açılışında olur. Kayma ve maliyet hep aleyhte varsayılır. Strateji t anından sonraki veriyi göremez
   (bozma testiyle korunur).
3. **Sinyal risk motorunu atlayamaz.** Emre giden tek yol risk motorunun onayıdır.
4. **Kaldıraç:** ölçülen Kelly'nin yarısı. Kodda sabit 3x tavanı var. **≥ 5x hiçbir modda yok.** Gerçek
   parada kaldıraç yalnız borsa ve hukuk kararından sonra açılır. Martingale ve kayıpta pozisyon büyütme yok.
5. **Otomasyon asimetriktir.** Riski azaltan her şey otomatik olabilir. İzni artıran her şey (canlıya alma,
   sermaye artırma, limit gevşetme) Scryne'ın açık onayını ister.
6. **Jev yargılar, kod uygular.** Jev çıktısı tek başına alım üretmez. Backtest içinde canlı Jev çağrısı
   yapılmaz, yargılar dondurulur (model sürümü + hash). Jev'e yön ya da fiyat sorulmaz.
7. **Deneme sayılır.** Her backtest koşusu deftere girer. Sonuca bakıp kural değiştirmek yeni bir denemedir.
8. **Sırlar:** API anahtarları `.env`'de ya da kullanıcı ortamında durur, git'e, loga ve panoya girmez.
   Borsa anahtarında çekim izni kapalıdır.
9. **Zaman UTC.** Bar zaman damgası açılış zamanıdır.
10. **Kendi hesabı, kendi parası.** Başkası adına işlem ya da sinyal paylaşımı yoktur.

## Dosyalar (ek)

- `docs/Arastirma.md` — kapsamlı araştırma (strateji kanıtı, mevzuat, maliyet, Jev, kaldıraç sınaması)
- `research/spikes/` — spike betikleri; raporları `docs/spikes/`
