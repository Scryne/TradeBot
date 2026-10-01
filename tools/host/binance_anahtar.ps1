# Binance API anahtarını host'un .env dosyasına yazar (Faz 12 gerçek kilit kolu). ANA BİLGİSAYARDA çalışır (PowerShell 7).
#   ./tools/host/binance_anahtar.ps1
# Anahtar ve gizli anahtar klavyeden sorulur; komut satırına, geçmişe, log'a ya da yerel diske yazılmaz (kural 12).
# Host'a SSH'ın standart girdisiyle gider, host'taki .env'de eski TRADEBOT_BINANCE_* satırlarının yerine yazılır.
# Sonra: `docker compose exec saglik tradebot paper binance-kontrol` ile salt okuma doğrulaması (emir göndermez).
param([string]$Hedef = 'tradebot-host')
$ErrorActionPreference = 'Stop'

$anahtar = Read-Host 'Binance API Key'
$gizliGuvenli = Read-Host 'Binance Secret Key' -AsSecureString
$gizli = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($gizliGuvenli))
if (-not $anahtar.Trim() -or -not $gizli.Trim()) { throw 'Anahtar ya da gizli anahtar boş' }

# Host'ta çalışacak betik (PowerShell 5.1): veriyi standart girdiden okur, .env'i BOM'suz UTF-8 yazar.
$uzak = @'
$yeni = [Console]::In.ReadToEnd() -split "`r?`n" | Where-Object { $_ }
$yol = 'C:\TradeBot\app\.env'
$eski = [IO.File]::ReadAllLines($yol) | Where-Object { $_ -notmatch '^TRADEBOT_BINANCE_(ANAHTAR|GIZLI)=' }
[IO.File]::WriteAllLines($yol, [string[]]($eski + $yeni), (New-Object Text.UTF8Encoding $false))
Write-Output "host .env güncellendi ($($yeni.Count) satır)"
'@
$kodlu = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($uzak))
"TRADEBOT_BINANCE_ANAHTAR=$($anahtar.Trim())`nTRADEBOT_BINANCE_GIZLI=$($gizli.Trim())" |
    ssh $Hedef "powershell -NoProfile -NonInteractive -EncodedCommand $kodlu"
if ($LASTEXITCODE -ne 0) { throw "host .env yazılamadı ($LASTEXITCODE)" }
Remove-Variable anahtar, gizli, gizliGuvenli
Write-Output 'Tamam. Doğrulama: ssh tradebot-host, sonra C:\TradeBot\app içinde: docker compose run --rm saglik tradebot paper binance-kontrol'
