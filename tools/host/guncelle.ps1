# TradeBot kodunu ev bilgisayarına (host) gönderir ve servisleri yeniden kurar. ANA BİLGİSAYARDA çalışır (PowerShell 7).
#   ./tools/host/guncelle.ps1 -Ilk     : host'ta çalışma kopyasını, rastgele parolalı .env'i ve güncelleme görevini oluşturur
#   ./tools/host/guncelle.ps1          : main dalını gönderir, host'ta çeker, servisleri kurar, sağlık raporu
#   ./tools/host/guncelle.ps1 -Kurma   : yalnız kodu gönderir
# Taşıma git bundle ile: Windows OpenSSH'ın cmd kabuğu git'in tek tırnaklı yolunu bozuyor, `git push` çalışmıyor.
# Docker adımı SSH'tan değil, kullanıcı oturumunda çalışan "TradeBot\Guncelle" görevinden yapılır: Docker Desktop
# kimlik araması SSH oturumunda "Belirtilen oturum yok" hatası veriyor (host'ta ölçüldü).
# Önkoşul: ~/.ssh/config içinde `tradebot-host` takma adı (docs/host/Kurulum.md).
param([switch]$Ilk, [switch]$Kurma, [string]$Hedef = 'tradebot-host', [int]$ZamanAsimiSn = 1500)
$ErrorActionPreference = 'Stop'
$kok = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
$dal = (git -C $kok rev-parse --abbrev-ref HEAD).Trim()
if ($dal -ne 'main') { throw "Yalnız main dalı gönderilir (şu an: $dal)" }
if (git -C $kok status --porcelain) { throw 'Commit edilmemiş değişiklik var; önce commit.' }

function Uzak([string]$komut) {
    ssh $Hedef $komut
    if ($LASTEXITCODE -ne 0) { throw "host komutu başarısız ($LASTEXITCODE): $komut" }
}

# 1) Bundle üret, gönder
$bundle = Join-Path ([IO.Path]::GetTempPath()) 'tradebot.bundle'
git -C $kok bundle create $bundle main
if ($LASTEXITCODE -ne 0) { throw 'bundle oluşturulamadı' }
scp -q $bundle "${Hedef}:C:/TradeBot/tradebot.bundle"
if ($LASTEXITCODE -ne 0) { throw 'bundle gönderilemedi' }
Remove-Item $bundle -Force
$surum = (git -C $kok rev-parse --short HEAD).Trim()

if ($Ilk) {
    # clone değil init + pull: klasörde .env (git dışı) önceden bulunabilir
    Uzak 'if not exist C:\TradeBot\app mkdir C:\TradeBot\app'
    Uzak 'cd /d C:\TradeBot\app && if not exist .git (git init -q -b main && git pull -q C:\TradeBot\tradebot.bundle main)'
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
}

# 2) Host'ta kodu çek
Uzak 'cd /d C:\TradeBot\app && git bundle verify -q C:\TradeBot\tradebot.bundle && git pull -q --ff-only C:\TradeBot\tradebot.bundle main && git log --oneline -1'

# 3) Güncelleme görevi (kullanıcı oturumunda, yalnız oturum açıkken; parola saklanmaz)
$gorev = 'powershell -NoProfile -Command "$a = New-ScheduledTaskAction -Execute powershell.exe -Argument ''-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\TradeBot\app\tools\host\host_guncelle.ps1''; $p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited; $s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew; Register-ScheduledTask -TaskPath \TradeBot\ -TaskName Guncelle -Action $a -Principal $p -Settings $s -Force | Out-Null"'
Uzak $gorev
if ($Ilk -or $Kurma) { Write-Host "Kod host'ta ($surum)." -ForegroundColor Green; return }

# 4) Görevi tetikle, bitmesini bekle, günlüğü getir
Uzak 'if exist C:\TradeBot\log\guncelle.son del C:\TradeBot\log\guncelle.son'
Uzak 'schtasks /run /tn \TradeBot\Guncelle >nul'
$bitis = (Get-Date).AddSeconds($ZamanAsimiSn)
do {
    Start-Sleep 10
    $sonuc = (ssh $Hedef 'if exist C:\TradeBot\log\guncelle.son type C:\TradeBot\log\guncelle.son' 2>$null | Out-String).Trim()
} until ($sonuc -or (Get-Date) -gt $bitis)
ssh $Hedef 'type C:\TradeBot\log\guncelle.log' 2>$null | Where-Object { $_ -notmatch '^\s*#\d+ |^ => ' }
if (-not $sonuc) { throw "Zaman aşımı ($ZamanAsimiSn sn): görev bitmedi. Oturum açık mı? (Görev yalnız oturum açıkken çalışır)" }
$kod, $saglik = $sonuc -split '\s+'
if ($kod -ne '0') { throw "docker compose başarısız ($kod)" }
Write-Host "Host güncel: $surum · sağlık çıkış kodu $saglik (0 = tümü OK, 1 = uyarı, 2 = hata)" -ForegroundColor Green

# 5) Son veritabanı yedeğini ana bilgisayara çek (evden ayrı kopya; SHA-256 doğrulanır, son 10 tutulur).
#    Yedek yoksa ya da çekilemezse dağıtım başarısız sayılmaz, uyarı yazılır.
$yerel = Join-Path $HOME 'TradeBot-yedek'
New-Item -ItemType Directory -Force $yerel | Out-Null
$sonJson = (ssh $Hedef 'if exist C:\TradeBot\yedek\son.json type C:\TradeBot\yedek\son.json' 2>$null | Out-String).Trim()
if (-not $sonJson) {
    Write-Host 'Yedek: host''ta henüz son.json yok (yedek servisi ilk yedeğini 02:15 UTC sonrasında alır).' -ForegroundColor Yellow
} else {
    $y = $sonJson | ConvertFrom-Json
    $hedefDosya = Join-Path $yerel $y.dosya
    if (-not (Test-Path $hedefDosya)) {
        scp -q "${Hedef}:C:/TradeBot/yedek/$($y.dosya)" $hedefDosya
        if ($LASTEXITCODE -ne 0 -or (Get-FileHash $hedefDosya -Algorithm SHA256).Hash.ToLower() -ne $y.sha256) {
            Remove-Item $hedefDosya -Force -ErrorAction SilentlyContinue
            Write-Host "Yedek: $($y.dosya) çekilemedi ya da SHA-256 tutmadı." -ForegroundColor Yellow
        }
    }
    Get-ChildItem $yerel -Filter 'tradebot-*.dump' | Sort-Object Name -Descending | Select-Object -Skip 10 | Remove-Item -Force
    Write-Host "Yedek: $($y.dosya) ($([math]::Round($y.bayt / 1MB)) MB, $($y.zaman)) → $yerel" -ForegroundColor Green
}
