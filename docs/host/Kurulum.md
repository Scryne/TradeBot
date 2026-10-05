---
proje: TradeBot
belge: Host kurulumu (ev bilgisayarı)
guncellendi: 2026-09-25
---
# Host kurulumu: evdeki ikinci bilgisayar

**Hedef:** Windows 11, 16 GB RAM, 1 TB disk ve kablolu bağlantılı ev bilgisayarı TradeBot'u 7/24 çalıştırsın.
Ana bilgisayardan SSH ile yönetilsin, telefondan Tailscale üzerinden izlensin.

Betikler: `tools/host/baslangic.ps1` (bir kez, elle), `tools/host/kurulum.ps1` (SSH ile),
`tools/host/guncelle.ps1` (kod gönderme, ana bilgisayardan).

## Adımlar

| # | Kim | Nerede | Ne |
| --- | --- | --- | --- |
| 1 | Scryne | Ev bilgisayarı BIOS'u (bir kez) | Sanallaştırma (Intel VT-x / AMD-V) **açık**. İsteğe bağlı: "Restore on AC Power Loss = Power On" |
| 2 | Scryne | Ev bilgisayarı, **yönetici** PowerShell | `baslangic.ps1` içeriğini çalıştır. OpenSSH kurulur, SSH yalnız yerel ağa açılır, ana bilgisayarın anahtarı eklenir. Çıktıdaki **kullanıcı adı ve IP**'yi Claude'a ilet |
| 3 | Claude | Ana bilgisayar | `~/.ssh/config`'e `tradebot-host` takma adı (IP, kullanıcı, `~/.ssh/tradebot_host` anahtarı); SSH ile bağlantı testi |
| 4 | Claude | SSH | `kurulum.ps1` (Kontrol) → rapor. Sonra `kurulum.ps1 -Uygula`: uyku kapalı, Windows Update yeniden başlatma kontrolü, **NTP**, WSL2, Docker Desktop, Git, Tailscale, `C:\TradeBot` |
| 5 | Scryne | Ev bilgisayarı ekranı (bir kez) | WSL kurulduysa yeniden başlat. Docker Desktop'ı bir kez aç (lisans onayı). Tailscale simgesinden oturum aç |
| 6 | Claude | SSH | `kurulum.ps1 -Uygula` tekrar → hepsi OK. Anahtarla giriş doğrulanınca `-SadeceAnahtar` (parola girişi kapanır) |
| 7 | Claude | Ana bilgisayar | `guncelle.ps1 -Ilk`: host'ta git deposu, çalışma kopyası ve rastgele parolalı `.env`. Anahtarlar `.env`'e eklenir (`TYPESAFE_API_KEY` vb.) |
| 8 | Claude | Ana bilgisayar | `guncelle.ps1`: kod gönderilir, `docker compose up -d --build`, `tradebot saglik` → **dns, saat, veritabanı, disk OK** |
| 9 | Scryne (karar) | — | Elektrik kesintisinden sonra kendiliğinden dönüş: BIOS AC ayarı + **otomatik oturum açma**. Docker Desktop yalnız oturum açıkken çalışır. Otomatik oturum, fiziksel erişimi olan herkese masaüstünü açar: güvenlik ↔ süreklilik kararı |

## Faz 1 host "bitti" kriteri

`tradebot saglik` host'ta çıkış kodu 0 ya da yalnız sır uyarısı ile dönmeli. Ayrıca:
- DNS < 1 sn,
- saat kayması < 0,25 sn,
- PostgreSQL bağlı ve denetim izi zinciri sağlam,
- disk ≥ 50 GB boş,
- `docker compose ps`'te `postgres` healthy, `saglik` running,
- yeniden başlatmadan sonra (oturum açılınca) servisler kendiliğinden dönüyor,
- ana bilgisayardan parolasız SSH, telefondan Tailscale erişimi.

## Kurulumda öğrenilenler (2026-09-25)

- `wsl --status` WSL kurulu değilken de 0 döndürüyor, `wsl --install` SSH oturumunda sessizce hiçbir şey yapmıyor.
  Bu yüzden `kurulum.ps1` WSL'yi DISM (bileşenler) ve GitHub'daki resmî MSI (paket) ile kurar.
- Windows OpenSSH'ın varsayılan cmd kabuğu, git'in tek tırnaklı uzak yolunu bozuyor (`git push` çalışmıyor).
  Bu yüzden kod `git bundle` ile taşınıyor (`guncelle.ps1`).
- Windows saat servisi varsayılan olarak 1 sn altı farkı saatler içinde kapatıyor. Yüksek doğruluk ayarlarıyla
  (UpdateInterval 100, poll 64 sn, MaxAllowedPhaseOffset 0) fark −720 ms'den ±0,3 ms'ye indi.
- Docker Desktop'ın kimlik araması SSH oturumunda çalışmıyor ("Belirtilen oturum yok"). Servis kurulumu kullanıcı
  oturumundaki `TradeBot\Guncelle` zamanlanmış görevinden yapılır (`host_guncelle.ps1`); SSH yalnız tetikler.
- WSL2 sanal makinesinin saati Windows'tan kopuk kalabiliyor (açılıştan sonra 335 ms geride, −3.643 ppm sapma).
  compose'daki `saat` servisi (chrony, yalnız `SYS_TIME` yetkisi) bunu sürekli düzeltir.
- **Otomatik oturum (Scryne'ın kararı: B, kilitsiz):** Sysinternals Autologon ile, parola LSA'da (kayıt defterinde
  düz metin yok). Microsoft hesabında "yalnız Windows Hello ile giriş" kapatıldı (`DevicePasswordLessBuildVersion=0`).
  Yeniden başlatma testi: açılış → otomatik oturum → servisler 57 sn'de geri.
- Host: 192.168.1.2 (yerel; DHCP, 2026-10-05 yeniden başlatmada .4 → .2 oldu. Bağlanamazsa `tradebot-host-ts`, sonra `ipconfig`), Tailscale 100.83.56.99. SSH takma adı `tradebot-host`.
- Ev dışından yönetim (2026-09-28): ana bilgisayara Tailscale (aynı hesap) + host'ta bir kez `tools/host/tailscale_ssh.ps1`
  (SSH'a 100.64.0.0/10'dan izin). Takma ad `tradebot-host-ts`; `guncelle.ps1 -Hedef tradebot-host-ts`.

## Yedek ve bekçi (2026-09-27 denetimi)

Denetimde veritabanının hiç yedeği olmadığı görüldü. Yedek bu yüzden Faz 9'dan öne alındı.

- **Yedek (compose `yedek`):** her gün 02:15 UTC'den sonra `pg_dump -Fc` alınır, `pg_restore --list` ile doğrulanır ve
  `C:\TradeBot\yedek` altına yazılır (WSL sanal diskinden ayrı dosya sistemi). 14 gün saklanır. `son.json` dosyası
  zamanı, boyutu ve SHA-256'yı tutar.
- **Evden ayrı kopya:** `guncelle.ps1` her dağıtımda son yedeği ana bilgisayara (`~/TradeBot-yedek`, son 10) çeker ve
  SHA-256'yı doğrular.
- **Geri yükleme:** önce boş bir veritabanına, sonra karşılaştırma:
  `docker compose exec -T postgres createdb -U tradebot tradebot_geri`, ardından
  `docker compose exec -T postgres pg_restore -U tradebot -d tradebot_geri /yedek/<dosya>`. Bunun için `postgres`
  servisine yedek dizini bağlı değildir, dosya `docker cp` ile konteynere kopyalanır.
- **Bekçi (compose `saglik`, 5 dakikada bir):** DNS, saat, veritabanı, disk ve sırları denetler. Host'ta ayrıca paper kalp
  atışına (son özkaynak işareti > 70 dk uyarı, > 2 sa hata), gece işine (> 26 sa uyarı, > 50 sa hata), yedek yaşına
  (> 26 sa hata) ve servis loglarındaki yeni `error` satırlarına bakar. Durum değişimini ve yeni hataları Telegram'a
  yollar; aynı olay saatte en fazla bir kez gider. Bekçi motordan bağımsız bir süreçtir: paper donarsa onu görür.
  Host'un tamamen kapanmasını göremez; bunun için dışarıda bir "ölü adam" denetimi Faz 9'da.
- **Telegram (Scryne, bir kez):** BotFather'da bot aç → token. Bota bir mesaj at →
  `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id`. İkisi host'taki `.env`'e yazılır:
  `TRADEBOT_TELEGRAM_TOKEN`, `TRADEBOT_TELEGRAM_SOHBET`. Token sırdır, git'e ve loga girmez.

## Güvenlik notları

- SSH yalnız "Özel" (ev) ağ profilinden ve yerel alt ağdan açık. İnternete port yönlendirmesi **yapılmaz**.
  Dışarıdan erişim yalnız Tailscale üzerinden.
- PostgreSQL portu dışarı açılmaz, yalnız konteynerler erişir.
- `.env` yalnız host'ta durur (git'te değil). PostgreSQL parolası rastgele üretilir ve ekrana yazılmaz.
- Anahtar dosyası `administrators_authorized_keys` yalnız Administrators ve SYSTEM tarafından okunabilir.
