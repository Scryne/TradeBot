# HOST'TA, kullanıcının masaüstü oturumunda çalışır ("TradeBot\Guncelle" zamanlanmış görevi, etkileşimli oturum).
# Neden: Docker Desktop kimlik araması yalnız kullanıcı oturumunda çalışıyor; SSH oturumunda
# "Belirtilen oturum yok" hatası veriyor. SSH görevi tetikler, bu betik işi yapar, sonucu dosyaya yazar.
$ErrorActionPreference = 'Continue'
# Docker çıktısı UTF-8; PowerShell 5.1 aksi halde OEM kod sayfasıyla okuyup Türkçe karakterleri bozuyor.
[Console]::OutputEncoding = [Text.Encoding]::UTF8
# Yerel komutların stderr'ini cmd üzerinden birleştir: PowerShell 5.1 aksi halde her satırı hata kaydına sarıyor.
function Calistir([string]$komut) { cmd.exe /c "$komut 2>&1" }
$logDizin = 'C:\TradeBot\log'
New-Item -ItemType Directory -Force $logDizin | Out-Null
$log = Join-Path $logDizin 'guncelle.log'
$son = Join-Path $logDizin 'guncelle.son'
Remove-Item $son -ErrorAction SilentlyContinue
Set-Location 'C:\TradeBot\app'
"=== $(Get-Date -Format o) ===" | Out-File $log -Encoding utf8
Calistir 'docker compose up -d --build' | Out-File $log -Append -Encoding utf8
$kod = $LASTEXITCODE
Calistir 'docker compose ps' | Out-File $log -Append -Encoding utf8
if ($kod -eq 0) {
    Calistir 'docker compose run --rm --no-deps saglik tradebot saglik' | Out-File $log -Append -Encoding utf8
    $saglik = $LASTEXITCODE
} else { $saglik = -1 }
"$kod $saglik" | Out-File $son -Encoding ascii
