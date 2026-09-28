# HOST'TA bir kez: panoyu (compose `pano`, yalnız 127.0.0.1:8080) Tailscale ağına HTTPS ile açar. İnternete açılmaz:
# yalnız aynı Tailscale hesabının cihazları (telefon, ana bilgisayar) erişir. LAN'daki başka cihazlar da erişemez.
#   ssh tradebot-host "powershell -NoProfile -ExecutionPolicy Bypass -File C:\TradeBot\app\tools\host\pano_tailscale.ps1"
# Tailnet'te HTTPS sertifikaları kapalıysa komut bir yönetim bağlantısı yazar: o bağlantıdan bir kez açılır.
# Kapatmak: tailscale serve --https=443 off
$ErrorActionPreference = 'Continue'
$ts = 'C:\Program Files\Tailscale\tailscale.exe'
& $ts serve --bg --https=443 http://127.0.0.1:8080
& $ts serve status
