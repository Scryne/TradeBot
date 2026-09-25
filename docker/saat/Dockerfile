# Docker/WSL2 sanal makinesinin saatini NTP ile senkron tutar. Bütün konteynerler bu çekirdek saati paylaşır.
# Neden: host yeniden başladıktan sonra Windows saati doğruyken sanal makine saati 335 ms geride ölçüldü.
# Yalnız SYS_TIME yetkisi verilir (privileged değil).
FROM alpine:3
RUN apk add --no-cache chrony
COPY chrony.conf /etc/chrony/chrony.conf
CMD ["chronyd", "-d", "-f", "/etc/chrony/chrony.conf"]
