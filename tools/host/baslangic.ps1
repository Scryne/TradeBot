# TradeBot host başlangıcı — EV BİLGİSAYARINDA, YÖNETİCİ PowerShell'de bir kez çalıştırılır.
# Yaptığı: OpenSSH sunucusunu kurar, yalnız yerel ağdan (ve ileride Tailscale'den) SSH'a izin verir,
# ana bilgisayarın TradeBot anahtarını yetkili anahtarlara ekler. Parola ile giriş açık kalır; anahtar
# çalıştığı doğrulanınca kurulum.ps1 kapatır.
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$AnaAnahtar = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFUSxYG5+Pmyp6F0kzugAs6qczSNZ6ruQW2d7ehRLpch tradebot-ana-bilgisayar'

Write-Host '1/5 OpenSSH sunucusu' -ForegroundColor Cyan
$yetenek = Get-WindowsCapability -Online -Name 'OpenSSH.Server*'
if ($yetenek.State -ne 'Installed') { Add-WindowsCapability -Online -Name $yetenek.Name | Out-Null }
Set-Service sshd -StartupType Automatic
Start-Service sshd

Write-Host '2/5 Ağ profili (ev ağı = Özel)' -ForegroundColor Cyan
Get-NetConnectionProfile | ForEach-Object {
    if ($_.NetworkCategory -eq 'Public') {
        Write-Host "   '$($_.Name)' ağı Genel -> Özel yapılıyor (ev ağı)"
        Set-NetConnectionProfile -InterfaceIndex $_.InterfaceIndex -NetworkCategory Private
    }
}

Write-Host '3/5 Güvenlik duvarı: SSH yalnız yerel ağdan' -ForegroundColor Cyan
Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue | Disable-NetFirewallRule
if (-not (Get-NetFirewallRule -Name 'TradeBot-SSH' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'TradeBot-SSH' -DisplayName 'TradeBot SSH (yerel ağ)' -Protocol TCP -LocalPort 22 `
        -Action Allow -Profile Private -RemoteAddress LocalSubnet | Out-Null
}

Write-Host '4/5 Ana bilgisayarın anahtarı' -ForegroundColor Cyan
$dosya = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
if (-not (Test-Path $dosya) -or -not (Select-String -Path $dosya -SimpleMatch $AnaAnahtar -Quiet)) {
    Add-Content -Path $dosya -Value $AnaAnahtar -Encoding ascii
}
icacls $dosya /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null
Restart-Service sshd

Write-Host '5/5 Bağlantı bilgisi (bunu ana bilgisayara ilet)' -ForegroundColor Cyan
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL' -and $_.PrefixOrigin -ne 'WellKnown' }).IPAddress
Write-Host "   Kullanıcı : $env:USERNAME"
Write-Host "   IP        : $($ip -join ', ')"
Write-Host "   Bilgisayar: $env:COMPUTERNAME"
Write-Host 'Tamam. Ana bilgisayardan SSH ile bağlanılabilir.' -ForegroundColor Green
