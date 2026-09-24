# TradeBot host kurulumu — ev bilgisayarında YÖNETİCİ olarak (SSH üzerinden de) çalışır. Windows PowerShell 5.1 uyumlu.
#   Kontrol (varsayılan): hiçbir şeyi değiştirmez, durumu raporlar.
#   -Uygula            : eksikleri düzeltir (idempotent; tekrar çalıştırmak güvenli).
#   -SadeceAnahtar     : SSH parola girişini kapatır (anahtarla girişin çalıştığı doğrulandıktan SONRA).
# Gerekçeler: docs/host/Kurulum.md, docs/spikes/02-nautilus.md (DNS, NTP).
#Requires -RunAsAdministrator
param([switch]$Uygula, [switch]$SadeceAnahtar)
$ErrorActionPreference = 'Stop'
$Sonuclar = New-Object System.Collections.Generic.List[object]
function Kayit($ad, $durum, $ayrinti) { $Sonuclar.Add([pscustomobject]@{ Kontrol = $ad; Durum = $durum; Ayrinti = $ayrinti }) }
function Indir($url, $hedef) { [Net.ServicePointManager]::SecurityProtocol = 'Tls12'; Invoke-WebRequest -Uri $url -OutFile $hedef -UseBasicParsing }

# --- Sistem ---------------------------------------------------------------------------------------
$os = Get-CimInstance Win32_OperatingSystem
$ramGb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$disk = Get-PSDrive C
Kayit 'sistem' 'BILGI' ("{0} {1} · RAM {2} GB · C: boş {3:N0} GB" -f $os.Caption, $os.Version, $ramGb, ($disk.Free / 1GB))
$sanal = (Get-CimInstance Win32_Processor | Select-Object -First 1).VirtualizationFirmwareEnabled
$hipervizor = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent  # Hyper-V çalışırken üstteki değer False döner
if ($sanal -or $hipervizor) { Kayit 'sanallastirma' 'OK' "BIOS sanallaştırma: $sanal · hipervizör çalışıyor: $hipervizor" }
else { Kayit 'sanallastirma' 'EKSIK' "BIOS'ta sanallaştırma (Intel VT-x / AMD-V) kapalı; WSL2 ve Docker için açılmalı" }

# --- Güç: uyku ve hazırda bekletme kapalı ---------------------------------------------------------
$uyku = (powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String 'Current AC Power Setting Index: (0x[0-9a-f]+)').Matches.Groups[1].Value
if ($uyku -ne '0x00000000') {
    if ($Uygula) { powercfg /change standby-timeout-ac 0; powercfg /change hibernate-timeout-ac 0; powercfg /change disk-timeout-ac 0; Kayit 'guc' 'DUZELTILDI' 'uyku/hazırda bekletme/disk kapatma: hiçbir zaman (prizde)' }
    else { Kayit 'guc' 'EKSIK' "prizdeyken uyku zaman aşımı $uyku (0 olmalı)" }
} else { Kayit 'guc' 'OK' 'prizdeyken uyku kapalı' }

# --- Windows Update: oturum açıkken kendiliğinden yeniden başlatma yok ---------------------------
$au = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
$nar = (Get-ItemProperty -Path $au -Name NoAutoRebootWithLoggedOnUsers -ErrorAction SilentlyContinue).NoAutoRebootWithLoggedOnUsers
if ($nar -ne 1) {
    if ($Uygula) { New-Item -Path $au -Force | Out-Null; Set-ItemProperty -Path $au -Name NoAutoRebootWithLoggedOnUsers -Value 1 -Type DWord; Kayit 'guncelleme' 'DUZELTILDI' 'oturum açıkken otomatik yeniden başlatma kapatıldı (güncellemeler yine iner; yeniden başlatmayı sen seçersin)' }
    else { Kayit 'guncelleme' 'EKSIK' 'Windows Update oturum açıkken yeniden başlatabilir' }
} else { Kayit 'guncelleme' 'OK' 'oturum açıkken otomatik yeniden başlatma kapalı' }

# --- Saat: NTP senkronu (Spike 02: ana bilgisayar 1,2 sn kaymış, senkron hiç yok) -----------------
$ntpKaynak = (w32tm /query /source 2>$null | Out-String).Trim()
if ($Uygula) {
    Set-Service W32Time -StartupType Automatic; Start-Service W32Time -ErrorAction SilentlyContinue
    w32tm /config /manualpeerlist:"time.cloudflare.com,0x9 time.google.com,0x9 pool.ntp.org,0x9" /syncfromflags:manual /reliable:yes /update | Out-Null
    # Yüksek doğruluk (Microsoft "1 sn altı" önerisi): sık yoklama, hızlı düzeltme; varsayılan ayarlar 1 sn altı
    # farkı saatler içinde kapatıyor (host'ta −0,72 sn ölçüldü, bu ayarlarla ±0,3 ms'ye indi).
    $w = 'HKLM:\SYSTEM\CurrentControlSet\Services\W32Time'
    Set-ItemProperty "$w\Config" -Name UpdateInterval -Value 100 -Type DWord
    Set-ItemProperty "$w\Config" -Name MinPollInterval -Value 6 -Type DWord
    Set-ItemProperty "$w\Config" -Name MaxPollInterval -Value 6 -Type DWord
    Set-ItemProperty "$w\Config" -Name MaxAllowedPhaseOffset -Value 0 -Type DWord
    Set-ItemProperty "$w\TimeProviders\NtpClient" -Name SpecialPollInterval -Value 64 -Type DWord
    w32tm /config /update | Out-Null
    Restart-Service W32Time; Start-Sleep 2; w32tm /resync /force | Out-Null; Start-Sleep 3
    $ntpKaynak = (w32tm /query /source 2>$null | Out-String).Trim()
}
$olcum = (w32tm /stripchart /computer:time.cloudflare.com /samples:3 /dataonly 2>$null | Select-String '([+-]\d+\.\d+)s' | Select-Object -Last 1)
$fark = if ($olcum) { [double]$olcum.Matches.Groups[1].Value } else { $null }
if ($fark -ne $null -and [math]::Abs($fark) -lt 0.1 -and $ntpKaynak -notmatch 'CMOS|Local') { Kayit 'saat' 'OK' ("kaynak {0}, Cloudflare'e göre {1:+0.000;-0.000} sn" -f $ntpKaynak, $fark) }
else { Kayit 'saat' ($(if ($Uygula) { 'UYARI' } else { 'EKSIK' })) ("kaynak '{0}', fark {1} sn (hedef < 0,1 sn; -Uygula NTP'yi kurar)" -f $ntpKaynak, $fark) }

# --- SSH ----------------------------------------------------------------------------------------
$sshd = Get-Service sshd -ErrorAction SilentlyContinue
$yapi = Join-Path $env:ProgramData 'ssh\sshd_config'
$parolaKapali = (Test-Path $yapi) -and (Select-String -Path $yapi -Pattern '^\s*PasswordAuthentication\s+no' -Quiet)
if ($SadeceAnahtar -and -not $parolaKapali) {
    (Get-Content $yapi) -replace '^\s*#?\s*PasswordAuthentication\s+\w+', 'PasswordAuthentication no' | Set-Content $yapi -Encoding ascii
    if (-not (Select-String -Path $yapi -Pattern '^\s*PasswordAuthentication\s+no' -Quiet)) { Add-Content $yapi 'PasswordAuthentication no' -Encoding ascii }
    Restart-Service sshd; $parolaKapali = $true
}
$sshDurum = if (-not $sshd -or $sshd.Status -ne 'Running') { 'EKSIK' } elseif ($parolaKapali) { 'OK' } else { 'UYARI' }
Kayit 'ssh' $sshDurum ("sshd {0}; parola girişi {1}" -f $(if ($sshd) { $sshd.Status } else { 'yok' }), $(if ($parolaKapali) { 'kapalı' } else { 'AÇIK (anahtar doğrulanınca -SadeceAnahtar)' }))

# --- WSL2 ---------------------------------------------------------------------------------------
# Not: `wsl --status` kurulu değilken de 0 döndürüyor ve `wsl --install` SSH oturumunda sessizce hiçbir şey
# yapmıyor (host'ta ölçüldü). Bu yüzden Windows bileşenleri DISM ile, WSL paketi GitHub'daki resmî MSI ile kurulur.
$bilesenler = 'Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform'
$durumlar = $bilesenler | ForEach-Object { (Get-WindowsOptionalFeature -Online -FeatureName $_).State.ToString() }
$paket = Test-Path "$env:ProgramFiles\WSL\wsl.exe"
if ($Uygula) {
    foreach ($b in $bilesenler) { dism.exe /online /enable-feature /featurename:$b /all /norestart | Out-Null }
    if (-not $paket) {
        $r = Invoke-RestMethod 'https://api.github.com/repos/microsoft/WSL/releases/latest' -UseBasicParsing
        $a = $r.assets | Where-Object name -match 'x64\.msi$' | Select-Object -First 1
        $m = Join-Path $env:TEMP $a.name; Indir $a.browser_download_url $m
        Start-Process msiexec.exe -ArgumentList '/i', $m, '/quiet', '/norestart' -Wait
        $paket = Test-Path "$env:ProgramFiles\WSL\wsl.exe"
    }
    $durumlar = $bilesenler | ForEach-Object { (Get-WindowsOptionalFeature -Online -FeatureName $_).State.ToString() }
}
$wslVar = $paket -and -not ($durumlar | Where-Object { $_ -ne 'Enabled' })
if ($wslVar) { Kayit 'wsl' 'OK' 'WSL bileşenleri açık, paket kurulu' }
elseif ($paket -and -not ($durumlar | Where-Object { $_ -notin 'Enabled', 'EnablePending' })) { Kayit 'wsl' 'YENIDEN_BASLAT' 'WSL kuruldu; bilgisayar yeniden başlatılmalı' }
else { Kayit 'wsl' 'EKSIK' ("bileşenler: {0}; paket: {1}" -f ($durumlar -join ', '), $paket) }

# --- Docker Desktop ------------------------------------------------------------------------------
$dockerYollari = @("$env:ProgramFiles\Docker\Docker\Docker Desktop.exe") + (Get-ChildItem 'C:\Users\*\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe' -ErrorAction SilentlyContinue | ForEach-Object FullName)
$dockerExe = $dockerYollari | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $dockerExe) {
    if ($Uygula -and $wslVar) {
        $kur = Join-Path $env:TEMP 'DockerDesktopInstaller.exe'
        Indir 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' $kur
        Start-Process $kur -ArgumentList 'install','--quiet','--accept-license','--backend=wsl-2','--always-run-service' -Wait
        Kayit 'docker' 'DUZELTILDI' 'Docker Desktop kuruldu; ilk açılış oturum içinde yapılmalı (ekrandan bir kez)'
    } else { Kayit 'docker' 'EKSIK' 'Docker Desktop kurulu değil (önce WSL)' }
} else {
    $ayarlar = Get-ChildItem 'C:\Users\*\AppData\Roaming\Docker\settings-store.json' -ErrorAction SilentlyContinue | Select-Object -First 1
    $oto = $false
    if ($ayarlar) {
        $j = Get-Content $ayarlar.FullName -Raw | ConvertFrom-Json
        $oto = [bool]$j.AutoStart
        if ($Uygula -and -not $oto) { $j | Add-Member -NotePropertyName AutoStart -NotePropertyValue $true -Force; [IO.File]::WriteAllText($ayarlar.FullName, ($j | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding $false)); $oto = $true }
    }
    Kayit 'docker' ($(if ($oto) { 'OK' } else { 'UYARI' })) ("kurulu: $dockerExe; oturum açılınca başlama: $oto")
}

# --- Git -----------------------------------------------------------------------------------------
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    if ($Uygula) {
        $api = Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest' -UseBasicParsing
        $url = ($api.assets | Where-Object { $_.name -match '^Git-.*-64-bit\.exe$' } | Select-Object -First 1).browser_download_url
        $kur = Join-Path $env:TEMP 'GitSetup.exe'; Indir $url $kur
        Start-Process $kur -ArgumentList '/VERYSILENT','/NORESTART','/NOCANCEL','/SP-','/COMPONENTS="gitlfs,assoc"' -Wait
        Kayit 'git' 'DUZELTILDI' "Git for Windows kuruldu (yeni oturumda PATH'te)"
    } else { Kayit 'git' 'EKSIK' 'git yok (kod güncellemesi için gerekli)' }
} else { Kayit 'git' 'OK' $git.Source }

# --- Tailscale -----------------------------------------------------------------------------------
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts -and (Test-Path "$env:ProgramFiles\Tailscale\tailscale.exe")) { $ts = "$env:ProgramFiles\Tailscale\tailscale.exe" }
if (-not $ts) {
    if ($Uygula) {
        $kur = Join-Path $env:TEMP 'tailscale.msi'; Indir 'https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi' $kur
        Start-Process msiexec.exe -ArgumentList '/i', $kur, '/quiet', '/norestart' -Wait
        Kayit 'tailscale' 'KULLANICI' 'kuruldu; giriş için ekranda Tailscale simgesinden oturum aç (bir kez)'
    } else { Kayit 'tailscale' 'EKSIK' 'Tailscale kurulu değil' }
} else {
    $durum = (& $ts status 2>&1 | Out-String)
    Kayit 'tailscale' ($(if ($durum -match 'Logged out|NeedsLogin|stopped') { 'KULLANICI' } else { 'OK' })) (($durum -split "`n")[0].Trim())
}

# --- Klasör ----------------------------------------------------------------------------------------
if (-not (Test-Path 'C:\TradeBot')) { if ($Uygula) { New-Item -ItemType Directory 'C:\TradeBot' | Out-Null; Kayit 'klasor' 'DUZELTILDI' 'C:\TradeBot oluşturuldu' } else { Kayit 'klasor' 'EKSIK' 'C:\TradeBot yok' } }
else { Kayit 'klasor' 'OK' 'C:\TradeBot' }

# --- Elektrik kesintisi sonrası: yalnız rapor (karar Scryne'ın) ------------------------------------
$wl = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' -ErrorAction SilentlyContinue
Kayit 'otomatik_oturum' 'BILGI' ("AutoAdminLogon={0}. Docker Desktop oturum açılınca başlar; elektrik gidip gelince sistemin kendiliğinden dönmesi için BIOS 'Restore on AC power loss = On' + otomatik oturum gerekir (karar senin)." -f $wl.AutoAdminLogon)

$Sonuclar | Format-Table -AutoSize -Wrap
$kotu = @($Sonuclar | Where-Object { $_.Durum -in 'EKSIK', 'YENIDEN_BASLAT' }).Count
if ($kotu -gt 0) { exit 1 } else { exit 0 }
