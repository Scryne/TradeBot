# TradeBot kodunu ev bilgisayarına (host) gönderir ve servisleri yeniden kurar. ANA BİLGİSAYARDA çalışır (PowerShell 7).
#   ./tools/host/guncelle.ps1 -Ilk     : host'ta depo ve çalışma kopyası oluşturur, .env'i hazırlar (bir kez)
#   ./tools/host/guncelle.ps1          : main dalını gönderir, host'ta çeker, `docker compose up -d --build`
# Önkoşul: ~/.ssh/config içinde `tradebot-host` takma adı (docs/host/Kurulum.md, adım 3).
param([switch]$Ilk, [string]$Hedef = 'tradebot-host')
$ErrorActionPreference = 'Stop'
$kok = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
$dal = (git -C $kok rev-parse --abbrev-ref HEAD).Trim()
if ($dal -ne 'main') { throw "Yalnız main dalı gönderilir (şu an: $dal)" }
if (git -C $kok status --porcelain) { throw 'Commit edilmemiş değişiklik var; önce commit.' }

function Uzak([string]$komut) {
    ssh $Hedef $komut
    if ($LASTEXITCODE -ne 0) { throw "host komutu başarısız ($LASTEXITCODE): $komut" }
}

if ($Ilk) {
    Uzak 'if not exist C:\TradeBot\repo.git git init --bare -b main C:\TradeBot\repo.git'
    if (-not (git -C $kok remote | Select-String -SimpleMatch 'host')) { git -C $kok remote add host "${Hedef}:C:/TradeBot/repo.git" }
    git -C $kok push host main
    Uzak 'if not exist C:\TradeBot\app git clone C:\TradeBot\repo.git C:\TradeBot\app'
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
    Write-Host 'İlk kurulum tamam. Anahtarları host''ta C:\TradeBot\app\.env içine ekle, sonra -Ilk olmadan çalıştır.' -ForegroundColor Green
    return
}

git -C $kok push host main
Uzak 'cd /d C:\TradeBot\app && git pull --ff-only && docker compose up -d --build && docker compose ps'
Uzak 'cd /d C:\TradeBot\app && docker compose run --rm --no-deps saglik tradebot saglik'
