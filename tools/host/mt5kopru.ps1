# MT5 köprüsü gözetmeni (Faz 8). HOST'TA, kullanıcı oturumunda çalışır: MT5 terminali grafik arayüzlü, SSH
# oturumunda açılmıyor (Spike 08). Hesap başına bir görev ("TradeBot\Mt5Kopru-forex|viop"), oturum açılınca başlar.
#   powershell -File C:\TradeBot\app\tools\host\mt5kopru.ps1 -Kaydet   : iki görevi kurar ve başlatır (SSH'tan olur)
#   (görev)  mt5kopru.ps1 -Hesap forex -Port 8765                        : köprüyü sonsuz döngüde çalıştırır
# Köprü takılırsa kendini sonlandırır (kopru.py takilma_sn); döngü terminali de kapatıp yeniden başlatır.
# Kod güncellemesi: host_guncelle.ps1 köprü süreçlerini sonlandırır, döngü yeni kodla açar.
param([switch]$Kaydet, [string]$Hesap, [int]$Port)
$ErrorActionPreference = 'Continue'
$HESAPLAR = @{ forex = 8765; viop = 8766 }

if ($Kaydet) {
    foreach ($h in $HESAPLAR.Keys) {
        $a = New-ScheduledTaskAction -Execute powershell.exe -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\TradeBot\app\tools\host\mt5kopru.ps1 -Hesap $h -Port $($HESAPLAR[$h])"
        $p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskPath \TradeBot\ -TaskName "Mt5Kopru-$h" -Action $a -Principal $p -Trigger $t -Settings $s -Force | Out-Null
        Start-ScheduledTask -TaskPath \TradeBot\ -TaskName "Mt5Kopru-$h"
        "Mt5Kopru-$h kuruldu, port $($HESAPLAR[$h])"
    }
    return
}

$env:PYTHONIOENCODING = 'utf-8'   # yönlendirilen çıktı aksi halde cp1254: Türkçe dışı karakterde köprü çöker
$log = "C:\TradeBot\log\mt5kopru-$Hesap.log"
$uv = "$env:USERPROFILE\.local\bin\uv.exe"
$kopru = 'C:\TradeBot\app\src\tradebot\mt5\kopru.py'
while ($true) {
    if ((Test-Path $log) -and (Get-Item $log).Length -gt 20MB) { Move-Item $log "$log.1" -Force }
    # temiz başlangıç: önceki (belki takılmış) terminal kapanır
    Get-Process terminal64 -EA SilentlyContinue | Where-Object { $_.Path -like "C:\TradeBot\mt5\$Hesap\*" } | Stop-Process -Force
    "{`"zaman`": `"$((Get-Date).ToUniversalTime().ToString('o'))`", `"olay`": `"gozetmen_baslatiyor`"}" | Out-File $log -Append -Encoding utf8
    cmd.exe /c "`"$uv`" run --no-project --python 3.12 --with MetaTrader5 `"$kopru`" --hesap $Hesap --port $Port >> `"$log`" 2>&1"
    "{`"zaman`": `"$((Get-Date).ToUniversalTime().ToString('o'))`", `"olay`": `"kopru_cikti`", `"kod`": $LASTEXITCODE}" | Out-File $log -Append -Encoding utf8
    Start-Sleep 15
}
