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
- Host: 192.168.1.4 (yerel), Tailscale 100.83.56.99. SSH takma adı `tradebot-host`.

## Güvenlik notları

- SSH yalnız "Özel" (ev) ağ profilinden ve yerel alt ağdan açık. İnternete port yönlendirmesi **yapılmaz**.
  Dışarıdan erişim yalnız Tailscale üzerinden.
- PostgreSQL portu dışarı açılmaz, yalnız konteynerler erişir.
- `.env` yalnız host'ta durur (git'te değil). PostgreSQL parolası rastgele üretilir ve ekrana yazılmaz.
- Anahtar dosyası `administrators_authorized_keys` yalnız Administrators ve SYSTEM tarafından okunabilir.
