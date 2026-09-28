# HOST'TA bir kez: panoyu (compose `pano`, yalnız 127.0.0.1:8080) Tailscale ağına açar. İnternete ve LAN'a açılmaz:
# yalnız aynı Tailscale hesabının cihazları (telefon, ana bilgisayar) erişir. Trafik WireGuard ile uçtan uca şifreli.
#   ssh tradebot-host "powershell -NoProfile -ExecutionPolicy Bypass -File C:\TradeBot\app\tools\host\pano_tailscale.ps1"
# Adres: http://scryne.tailca7928.ts.net/ (2026-09-28). Kalıcıdır (--bg), host yeniden başlasa da sürer.
# HTTPS (isteğe bağlı): tailnet'te sertifika kapalı (2026-09-28). Tailscale yönetim panelinden DNS › HTTPS
# Certificates açılırsa `--https=443` ile değiştirilebilir; kapalıyken o komut onay bekleyip takılır.
# Kapatmak: tailscale serve --http=80 off
$ErrorActionPreference = 'Continue'
$ts = 'C:\Program Files\Tailscale\tailscale.exe'
& $ts serve --bg --http=80 http://127.0.0.1:8080
& $ts serve status
