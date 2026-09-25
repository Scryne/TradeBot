# TradeBot kodunu ev bilgisayarına (host) gönderir ve servisleri yeniden kurar. ANA BİLGİSAYARDA çalışır (PowerShell 7).
#   ./tools/host/guncelle.ps1 -Ilk     : host'ta çalışma kopyasını ve rastgele parolalı .env'i oluşturur (bir kez)
#   ./tools/host/guncelle.ps1          : main dalını gönderir, host'ta çeker, `docker compose up -d --build`, sağlık raporu
# Taşıma git bundle ile: Windows OpenSSH'ın cmd kabuğu git'in tek tırnaklı yolunu bozduğu için ('C:/..' bulunamıyor)
# doğrudan `git push` çalışmıyor. Bundle tek dosya, `git bundle verify` ile doğrulanır.
# Önkoşul: ~/.ssh/config içinde `tradebot-host` takma adı (docs/host/Kurulum.md, adım 3).
param([switch]$Ilk, [switch]$Kurma, [string]$Hedef = 'tradebot-host')
$ErrorActionPreference = 'Stop'
$kok = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
$dal = (git -C $kok rev-parse --abbrev-ref HEAD).Trim()
if ($dal -ne 'main') { throw "Yalnız main dalı gönderilir (şu an: $dal)" }
if (git -C $kok status --porcelain) { throw 'Commit edilmemiş değişiklik var; önce commit.' }

function Uzak([string]$komut) {
    ssh $Hedef $komut
    if ($LASTEXITCODE -ne 0) { throw "host komutu başarısız ($LASTEXITCODE): $komut" }
}

# 1) Bundle üret ve gönder
$bundle = Join-Path ([IO.Path]::GetTempPath()) 'tradebot.bundle'
git -C $kok bundle create $bundle main
if ($LASTEXITCODE -ne 0) { throw 'bundle oluşturulamadı' }
scp -q $bundle "${Hedef}:C:/TradeBot/tradebot.bundle"
if ($LASTEXITCODE -ne 0) { throw 'bundle gönderilemedi' }
Remove-Item $bundle -Force
if (-not $Ilk) { Uzak 'cd /d C:\TradeBot\app && git bundle verify -q C:\TradeBot\tradebot.bundle' }  # depo içinde çalışır
$surum = (git -C $kok rev-parse --short HEAD).Trim()

if ($Ilk) {
    # clone değil init + pull: klasörde .env (git dışı) önceden bulunabilir
    Uzak 'if not exist C:\TradeBot\app mkdir C:\TradeBot\app'
    Uzak 'cd /d C:\TradeBot\app && if not exist .git (git init -q -b main && git pull -q C:\TradeBot\tradebot.bundle main)'
    # .env: rastgele PostgreSQL parolasıyla yerelde geçici üretilir, host'ta yoksa gönderilir, yerel kopya silinir.
    ssh $Hedef 'if exist C:\TradeBot\app\.env (exit 1) else (exit 0)'
    if ($LASTEXITCODE -eq 0) {
        $gecici = New-TemporaryFile
        try {
            $parola = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)) -replace '[+/=]', ''
            (Get-Content (Join-Path $kok '.env.example')) -replace '^POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$parola" |
                Set-Content $gecici -Encoding ascii
            scp -q $gecici "${Hedef}:C:/TradeBot/app/.env"
            if ($LASTEXITCODE -ne 0) { throw '.env gönderilemedi' }
        } finally { Remove-Item $gecici -Force }
    }
    Write-Host "Host çalışma kopyası hazır ($surum). Anahtarları C:\TradeBot\app\.env içine ekle." -ForegroundColor Green
    return
}

Uzak 'cd /d C:\TradeBot\app && git pull -q --ff-only C:\TradeBot\tradebot.bundle main && git log --oneline -1'
if ($Kurma) { return }
# SSH oturumunda Windows Credential Manager yok ("Belirtilen oturum yok"): TradeBot komutları kimlik deposu olmayan
# ayrı bir Docker yapılandırmasıyla çalışır (imajlar herkese açık). Kullanıcının kendi Docker ayarına dokunulmaz.
$dk = 'set DOCKER_CONFIG=C:\TradeBot\docker-config&& cd /d C:\TradeBot\app &&'
Uzak 'if not exist C:\TradeBot\docker-config mkdir C:\TradeBot\docker-config & if not exist C:\TradeBot\docker-config\config.json (echo {}> C:\TradeBot\docker-config\config.json)'
Uzak "$dk docker compose up -d --build && docker compose ps"
ssh $Hedef "$dk docker compose run --rm --no-deps saglik tradebot saglik"
Write-Host "Host güncel: $surum" -ForegroundColor Green
