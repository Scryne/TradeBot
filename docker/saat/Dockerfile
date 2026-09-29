# Docker/WSL2 sanal makinesinin saatini NTP ile senkron tutar. Bütün konteynerler bu çekirdek saati paylaşır.
# Neden: host yeniden başladıktan sonra Windows saati doğruyken sanal makine saati 335 ms geride ölçüldü.
# Yalnız SYS_TIME yetkisi verilir (privileged değil).
FROM alpine:3
RUN apk add --no-cache chrony
COPY chrony.conf /etc/chrony/chrony.conf
# Konteyner yeniden başlayınca eski PID dosyası (pid=1) kalıyor ve chronyd "Another chronyd may already be running"
# diyerek çıkıyor (2026-09-29: saatlerce yeniden başlama döngüsü). Başlamadan önce silinir.
CMD ["sh", "-c", "rm -f /run/chrony/chronyd.pid && exec chronyd -d -f /etc/chrony/chrony.conf"]
