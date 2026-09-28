# HOST'TA bir kez: panoyu (compose `pano`, yalnız 127.0.0.1:8080) Tailscale ağına açar. İnternete ve LAN'a açılmaz:
# yalnız aynı Tailscale hesabının cihazları erişir. Trafik WireGuard ile uçtan uca şifreli.
#   ssh tradebot-host "powershell -NoProfile -ExecutionPolicy Bypass -File C:\TradeBot\app\tools\host\pano_tailscale.ps1"
# Adres: http://scryne.tailca7928.ts.net:8080/ (2026-09-29). Kalıcıdır (--bg), host yeniden başlasa da sürer.
#
# Neden düz TCP (2026-09-29, Tailscale 1.102.4, Windows): `--http=80` ve `--https=443` host'un kendi içinden 200
# veriyor, uzak cihazdan gelen istekte ise isim eşleşmesi başarısız ("TLS handshake error: no webserver configured
# for name/port", HTTP'de 404/askı). `--tcp` isim eşleştirmez, çalışıyor. Güvenlik duvarı kuralı gerekmez
# (trafiği tailscaled kendi yığınında karşılar).
# Ön koşul: host Tailscale'i unattended modda (`tailscale up --unattended`, 2026-09-29): servis masaüstü oturumuna
# bağlı kalmaz; aksi halde servis yeniden başlayınca NoState'te kalır ve serve ayarı kaybolur.
# Kapatmak: tailscale serve --tcp=8080 off
$ErrorActionPreference = 'Continue'
$ts = 'C:\Program Files\Tailscale\tailscale.exe'
& $ts serve --bg --tcp=8080 tcp://127.0.0.1:8080
& $ts serve status
