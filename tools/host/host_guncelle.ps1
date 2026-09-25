# HOST'TA, kullanıcının masaüstü oturumunda çalışır ("TradeBot\Guncelle" zamanlanmış görevi, etkileşimli oturum).
# Neden: Docker Desktop kimlik araması yalnız kullanıcı oturumunda çalışıyor; SSH oturumunda
# "Belirtilen oturum yok" hatası veriyor. SSH görevi tetikler, bu betik işi yapar, sonucu dosyaya yazar.
$ErrorActionPreference = 'Continue'
$logDizin = 'C:\TradeBot\log'
New-Item -ItemType Directory -Force $logDizin | Out-Null
$log = Join-Path $logDizin 'guncelle.log'
$son = Join-Path $logDizin 'guncelle.son'
Remove-Item $son -ErrorAction SilentlyContinue
Set-Location 'C:\TradeBot\app'
"=== $(Get-Date -Format o) ===" | Out-File $log -Encoding utf8
& docker compose up -d --build 2>&1 | Out-File $log -Append -Encoding utf8
$kod = $LASTEXITCODE
& docker compose ps 2>&1 | Out-File $log -Append -Encoding utf8
if ($kod -eq 0) {
    & docker compose run --rm --no-deps saglik tradebot saglik 2>&1 | Out-File $log -Append -Encoding utf8
    $saglik = $LASTEXITCODE
} else { $saglik = -1 }
"$kod $saglik" | Out-File $son -Encoding ascii
