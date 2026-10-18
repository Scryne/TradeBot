# Alpaca PAPER API anahtarını host'un .env dosyasına yazar (Nasdaq kolu). ANA BİLGİSAYARDA çalışır (PowerShell 7).
#   ./tools/host/alpaca_anahtar.ps1
# Anahtar ve gizli anahtar klavyeden sorulur; komut satırına, geçmişe, log'a ya da yerel diske yazılmaz (kural 12).
# Host'a SSH'ın standart girdisiyle gider, host'taki .env'de eski TRADEBOT_ALPACA_* satırlarının yerine yazılır.
# Yalnız PAPER anahtarı (app.alpaca.markets → Paper Trading → API Keys): kod yalnız paper-api.alpaca.markets'e bağlanır.
# Sonra: `docker compose run --rm saglik tradebot paper alpaca-kontrol` ile salt okuma doğrulaması (emir göndermez) ve
# `docker compose restart nasdaq` (düğüm açılışta anahtarı görürse Alpaca paper'a geçer).
param([string]$Hedef = 'tradebot-host')
$ErrorActionPreference = 'Stop'

$anahtar = Read-Host 'Alpaca PAPER API Key ID'
$gizliGuvenli = Read-Host 'Alpaca PAPER Secret Key' -AsSecureString
$gizli = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($gizliGuvenli))
if (-not $anahtar.Trim() -or -not $gizli.Trim()) { throw 'Anahtar ya da gizli anahtar boş' }
if (-not $anahtar.Trim().StartsWith('PK')) { throw 'Paper anahtarları PK ile başlar; canlı (AK…) anahtar kullanılmaz' }

# Host'ta çalışacak betik (PowerShell 5.1): veriyi standart girdiden okur, .env'i BOM'suz UTF-8 yazar.
$uzak = @'
$yeni = [Console]::In.ReadToEnd() -split "`r?`n" | Where-Object { $_ }
$yol = 'C:\TradeBot\app\.env'
$eski = [IO.File]::ReadAllLines($yol) | Where-Object { $_ -notmatch '^TRADEBOT_ALPACA_(ANAHTAR|GIZLI)=' }
[IO.File]::WriteAllLines($yol, [string[]]($eski + $yeni), (New-Object Text.UTF8Encoding $false))
Write-Output "host .env güncellendi ($($yeni.Count) satır)"
'@
$kodlu = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($uzak))
"TRADEBOT_ALPACA_ANAHTAR=$($anahtar.Trim())`nTRADEBOT_ALPACA_GIZLI=$($gizli.Trim())" |
    ssh $Hedef "powershell -NoProfile -NonInteractive -EncodedCommand $kodlu"
if ($LASTEXITCODE -ne 0) { throw "host .env yazılamadı ($LASTEXITCODE)" }
Remove-Variable anahtar, gizli, gizliGuvenli
Write-Output 'Tamam. Doğrulama: ssh tradebot-host, sonra C:\TradeBot\app içinde: docker compose run --rm saglik tradebot paper alpaca-kontrol'
