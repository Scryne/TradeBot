# Spike 08'i host'ta kullanıcı oturumunda çalıştırır (MT5 grafik arayüzlü; SSH oturumunda açılmaz).
# Ana bilgisayardan:
#   scp research/spikes/08_mt5/* tradebot-host:C:/TradeBot/spike08/
#   ssh tradebot-host "powershell -NoProfile -File C:\TradeBot\spike08\calistir.ps1 -Kaydet"   (görevi kurar ve tetikler)
# Görev, `argumanlar.txt`'deki her satırı (ör. "forex", "viop", "forex --emir XAUUSD") sırayla çalıştırır.
#   -Baslangic '2026-09-28 10:00' (host yerel saati): hemen değil, o anda bir kez çalışır (piyasa açıkken ölçüm)
param([switch]$Kaydet, [string]$Baslangic)
$ErrorActionPreference = 'Stop'
$d = 'C:\TradeBot\spike08'
if ($Kaydet) {
    $a = New-ScheduledTaskAction -Execute powershell.exe -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $d\calistir.ps1"
    $p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 60) -MultipleInstances IgnoreNew
    $t = if ($Baslangic) { New-ScheduledTaskTrigger -Once -At ([datetime]$Baslangic) } else { $null }
    $ek = if ($t) { @{ Trigger = $t } } else { @{} }
    Register-ScheduledTask -TaskPath \TradeBot\ -TaskName Spike08 -Action $a -Principal $p -Settings $s -Force @ek | Out-Null
    Remove-Item "$d\bitti.txt" -ErrorAction SilentlyContinue
    if (-not $Baslangic) { Start-ScheduledTask -TaskPath \TradeBot\ -TaskName Spike08 }
    return
}
# PowerShell 5.1: yerel komutun stderr'i (uv indirme çıktısı) 'Stop' altında betiği öldürür
$ErrorActionPreference = 'Continue'
$log = "$d\calistir.log"
"$(Get-Date -Format o) basladi" | Out-File $log -Encoding utf8
$uv = "$env:USERPROFILE\.local\bin\uv.exe"
# MT5 köprüsü (tools/host/mt5kopru.ps1) aynı terminalleri kullanır: spike boyunca durur, sonunda yeniden başlar
$kopruler = @(Get-ScheduledTask -TaskPath \TradeBot\ -EA SilentlyContinue | Where-Object TaskName -like 'Mt5Kopru-*')
$kopruler | Disable-ScheduledTask | Out-Null
$kopruler | Stop-ScheduledTask
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'mt5kopru\.ps1|mt5\\kopru\.py' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }
Get-Process terminal64 -EA SilentlyContinue | Where-Object { $_.Path -like 'C:\TradeBot\mt5\*' } | Stop-Process -Force
foreach ($satir in Get-Content "$d\argumanlar.txt") {
    if (-not $satir.Trim()) { continue }
    "--- $satir" | Out-File $log -Append -Encoding utf8
    $argv = @('run', '--no-project', '--python', '3.12', '--with', 'MetaTrader5', "$d\baglanti.py") + ($satir -split '\s+')
    # her hesap 20 dk (10 dk örnekleme + emir): MT5 çağrısı takılırsa (ikinci turda oldu) görev sonsuza kadar beklemesin
    $p = Start-Process $uv -ArgumentList $argv -NoNewWindow -PassThru -RedirectStandardOutput "$d\cikti.txt" -RedirectStandardError "$d\hata.txt"
    if (-not $p.WaitForExit(1200000)) { $p | Stop-Process -Force; "zaman asimi" | Out-File $log -Append -Encoding utf8 }
    Get-Content "$d\cikti.txt", "$d\hata.txt" | Out-File $log -Append -Encoding utf8
    "cikis $($p.ExitCode)" | Out-File $log -Append -Encoding utf8
    # mt5.shutdown() terminali kapatmaz; sonraki tur temiz başlasın (takılan python da)
    Get-Process terminal64, python -EA SilentlyContinue | Where-Object { $_.Path -like 'C:\TradeBot\mt5\*' -or $_.Path -like '*\uv\*' } | Stop-Process -Force
}
$kopruler | Enable-ScheduledTask | Out-Null
$kopruler | Start-ScheduledTask
"$(Get-Date -Format o) bitti" | Out-File "$d\bitti.txt" -Encoding utf8
