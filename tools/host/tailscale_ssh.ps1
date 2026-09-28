# HOST'TA, yönetici PowerShell'de bir kez: SSH'a Tailscale ağından (100.64.0.0/10) da izin verir.
# Neden (2026-09-28): ana bilgisayar ev ağı dışındayken host'a ulaşılamıyordu; kural yalnız yerel ağa (LocalSubnet)
# izin veriyordu. Tailscale adresleri yalnız aynı hesabın cihazlarına açıktır; SSH yine yalnız anahtarla.
# Ana bilgisayarda: Tailscale kurulu ve aynı hesapla oturum açık olmalı; SSH takma adı `tradebot-host-ts` (100.83.56.99).
#   ssh tradebot-host "powershell -NoProfile -ExecutionPolicy Bypass -File C:\TradeBot\app\tools\host\tailscale_ssh.ps1"
$ErrorActionPreference = 'Stop'
if (-not (Get-NetFirewallRule -Name 'TradeBot-SSH-Tailscale' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'TradeBot-SSH-Tailscale' -DisplayName 'TradeBot SSH (Tailscale)' -Protocol TCP -LocalPort 22 `
        -Action Allow -Profile Any -RemoteAddress 100.64.0.0/10 | Out-Null
}
Get-NetFirewallRule -Name 'TradeBot-SSH*' | Select-Object Name, Enabled, Profile | Format-Table -AutoSize
