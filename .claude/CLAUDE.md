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

Kurumsal, çok piyasalı, tamamen otonom bir trade sistemi (Scryne'ın kendi hesabı). İlk aşama yalnız paper.
Aşağıdakiler tercih değil, kısıttır. Bir görev bunlardan birini ihlal ediyorsa görev yanlıştır.
Gerekçeler: `docs/Final-Dokuman.md` ve `docs/Arastirma.md`.

1. **ScryneQuant kaynak olarak okunabilir.** 2026-09-24'teki "bakılmaz" kararını Scryne 2026-10-05'te kaldırdı:
   "oradan bizde eksik olan bir şey var ise alabilirsin". Alınan her şey TradeBot'un kurallarıyla yeniden ölçülür.
2. **Önce konuş, sonra yap.** Yön ya da kapsam değiştiren her şey Scryne'la konuşulup karara bağlanmadan
   dokümana ya da koda girmez.
3. **Saf karar çekirdeği.** Strateji mantığı I/O yapmaz, yalnız t anına kadar kesilmiş veriyi görür (bozma
   testiyle korunur). Vektörel tarama ve Nautilus aynı fonksiyonu çağırır (parity testi).
4. **Gerçekçi yürütme.** Karar kapanmış barla verilir, dolum sonraki barın açılışında olur. Kayma ve maliyet
   hep aleyhte varsayılır. Maliyet modeli piyasa başınadır.
5. **Sinyal risk motorunu atlayamaz.** Emre giden tek yol risk onayıdır. Engelleyen katman risk motorunun
   dışında olabilir, izin veren katman olamaz.
6. **Kaldıraç:** yarım Kelly. Kodda sabit 3x tavan vardır. **≥ 5x hiçbir modda yok** (agresif gözlem kolu
   dahil). Martingale ve kayıpta pozisyon büyütme yoktur.
7. **Otomasyon asimetriktir.** Riski azaltan her şey otomatiktir (veto, fren, kol durdurma, acil durdurma).
   Acil durdurma sonrası yeniden başlatma, gerçek paraya geçiş ve tavan değişikliği Scryne'ın açık onayını
   ister.
8. **Jev yargılar, kod uygular.** Jev ve yükseltme modeli (NVIDIA) yalnız riski azaltabilir. Yön, fiyat,
   boyut ve emir kararı verdirilmez. Backtest içinde canlı model çağrısı yapılmaz, yargılar dondurulur
   (model sürümü + soru hash'i + girdi hash'i). Belirsiz durumda: riski azalt ve alarm ver.
9. **Veri:** ham veri değişmez, hash'i kimliğidir. Evren point-in-time tutulur. Metinlerde zaman ilk yayın
   zamanıdır. Kurumsal işlem düzeltmeleri hamdan yeniden üretilir.
10. **Deneme sayılır.** Her tarama ya da backtest koşusu deneme defterine girer. Sonuca bakıp kural
    değiştirmek yeni bir denemedir.
11. **Zaman UTC.** Bar zaman damgası açılış zamanıdır. Piyasa takvimleri enstrüman kaydındadır.
12. **Sırlar** yalnız host'ta tutulur: git'e, log'a ve panoya girmez. Borsa anahtarında çekim izni kapalıdır.
13. **Kendi hesabı, kendi parası.** Başkası adına işlem, sinyal paylaşımı ya da ürünleştirme yoktur.

## Dosyalar (ek)

- `docs/Final-Dokuman.md` — bağlayıcı kararlar (⚑ işaretliler Faz 0 spike'larıyla kesinleşir)
- `docs/Arastirma.md` — kapsamlı araştırma (strateji kanıtı, mevzuat, maliyet, Jev, kaldıraç, çok piyasa eki)
- `research/spikes/` — spike betikleri; raporları `docs/spikes/`
