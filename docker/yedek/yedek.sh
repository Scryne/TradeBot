#!/bin/sh
# Veritabanı yedeği (compose `yedek`). Günde bir, SAAT'ten (UTC HHMM) sonra; o günün yedeği yoksa açılışta hemen.
# pg_dump özel biçim → pg_restore --list ile doğrulanır → yerine taşınır → son.json (zaman, boyut, sha256) → SAKLA günden
# eskiler silinir. Hata: son_hata.json; sağlık bekçisi son.json yaşına bakar (> 26 saat → alarm).
set -u
SAAT="${SAAT:-0215}"
SAKLA="${SAKLA:-14}"
D=/yedek

yedekle() {
    # Host açılışında Docker konteynerleri depends_on sırası gözetmeden kaldırır: postgres hazır olmadan pg_dump denenirse
    # her açılışta sahte KRİTİK alarm gider (2026-10-22/23). En çok 5 dk beklenir; hâlâ hazır değilse gerçek hata yazılır.
    i=0
    until pg_isready -q || [ "$i" -ge 60 ]; do i=$((i + 1)); sleep 5; done
    f="$D/tradebot-$(date -u +%Y%m%dT%H%MZ).dump"
    if pg_dump -Fc -f "$f.tmp" && pg_restore --list "$f.tmp" > /dev/null; then
        mv "$f.tmp" "$f"
        printf '{"dosya":"%s","bayt":%s,"sha256":"%s","zaman":"%s"}\n' "$(basename "$f")" "$(stat -c%s "$f")" \
            "$(sha256sum "$f" | cut -d' ' -f1)" "$(date -u +%FT%TZ)" > "$D/son.json.tmp" && mv "$D/son.json.tmp" "$D/son.json"
        ls -1t "$D"/tradebot-*.dump | tail -n +"$((SAKLA + 1))" | xargs -r rm -f
        echo "yedek tamam: $(cat "$D/son.json")"
    else
        rm -f "$f.tmp"
        printf '{"zaman":"%s","hata":"pg_dump ya da doğrulama başarısız"}\n' "$(date -u +%FT%TZ)" > "$D/son_hata.json"
        echo "YEDEK HATASI" >&2
    fi
}

mkdir -p "$D"
while true; do
    if [ "$(date -u +%H%M)" -ge "$SAAT" ] && ! ls "$D"/tradebot-"$(date -u +%Y%m%d)"T*.dump > /dev/null 2>&1; then
        yedekle
    fi
    sleep 300
done
