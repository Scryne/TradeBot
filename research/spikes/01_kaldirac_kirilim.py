"""Kaldıraçlı Donchian kırılımı — bağımsız, açıklayıcı sınama (ön kayıtsız, parametre taraması yok).

Kural (klasik Turtle benzeri, önceden sabit): giriş = kapanış > önceki 20 günün en yükseği (long) /
< önceki 20 günün en düşüğü (short); çıkış = ters yönde 10 günlük kanal kırılımı. Karar kapanmış barla,
dolum sonraki günün açılışında. Maliyet: taraf başı %0,05 (perp taker) + %0,02 kayma; funding: pozisyon
açıkken yıllık %10 (long öder, short alır, kaba ortalama). Kaldıraç: tüm özkaynak izole teminat, giriş
anında L kat notional; işlem içinde gün içi en kötü fiyat giriş fiyatından 1/L - %0,5 kadar aleyhteyse
likidasyon (işlemin teminatı sıfırlanır → özkaynak sıfır = iflas).
"""
import json, math, urllib.request, time

def indir(sembol):
    url = "https://api.binance.com/api/v3/klines?symbol={}&interval=1d&limit=1000&startTime={}"
    t, satir = 1502928000000, []
    while True:
        with urllib.request.urlopen(url.format(sembol, t), timeout=30) as r:
            p = json.load(r)
        if not p:
            break
        satir += p
        t = p[-1][0] + 86400000
        if len(p) < 1000:
            break
        time.sleep(0.2)
    return [(k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4])) for k in satir]

def kos(bar, L, yonler=("long",), kanal_gir=20, kanal_cik=10):
    ucret, kayma, funding_gun = 0.0005, 0.0002, 0.10 / 365
    oz, tepe, en_dd, likit, islem = 1.0, 1.0, 0.0, 0, 0
    poz, giris = 0, None
    for i in range(kanal_gir + 1, len(bar) - 1):
        _, o, h, l, c = bar[i]
        # açık pozisyonun gün içi likidasyon kontrolü (bugünün barı)
        if poz != 0:
            kotu = (giris - l) / giris if poz > 0 else (h - giris) / giris
            if kotu >= 1 / L - 0.005:
                oz, poz, likit, en_dd = 0.0, 0, likit + 1, -1.0
                break
        yuksek = max(b[2] for b in bar[i - kanal_gir:i])
        dusuk = min(b[3] for b in bar[i - kanal_gir:i])
        cik_y = max(b[2] for b in bar[i - kanal_cik:i])
        cik_d = min(b[3] for b in bar[i - kanal_cik:i])
        hedef = poz
        if poz > 0 and c < cik_d: hedef = 0
        if poz < 0 and c > cik_y: hedef = 0
        if hedef == 0:
            if c > yuksek and "long" in yonler: hedef = 1
            elif c < dusuk and "short" in yonler: hedef = -1
        acilis = bar[i + 1][1]
        if hedef != poz:
            if poz != 0:  # kapat
                cikis = acilis * (1 - kayma * poz)
                getiri = poz * (cikis / giris - 1)
                oz *= max(0.0, 1 + L * getiri - L * ucret)
                islem += 1
            if hedef != 0:  # aç
                giris = acilis * (1 + kayma * hedef)
                oz *= 1 - L * ucret
            poz = hedef
        if poz != 0:
            oz *= 1 - L * funding_gun * poz  # long öder, short alır
        # işaretli özkaynak (düşüş ölçümü için)
        isaretli = oz * (1 + L * poz * (c / giris - 1)) if poz != 0 else oz
        tepe = max(tepe, isaretli)
        en_dd = min(en_dd, isaretli / tepe - 1)
        if oz <= 0:
            break
    yil = (bar[-1][0] - bar[kanal_gir][0]) / (365.25 * 86400000)
    cagr = oz ** (1 / yil) - 1 if oz > 0 else -1.0
    return dict(L=L, son=oz, cagr=cagr, dd=en_dd, likit=likit, islem=islem, yil=round(yil, 1))

if __name__ == "__main__":
    for s in ("BTCUSDT", "ETHUSDT"):
        bar = indir(s)
        print(f"\n{s}: {len(bar)} gün, {time.strftime('%Y-%m-%d', time.gmtime(bar[0][0]/1000))} → "
              f"{time.strftime('%Y-%m-%d', time.gmtime(bar[-1][0]/1000))}")
        al_tut = bar[-1][4] / bar[21][4]
        print(f"  al-tut (1x, maliyetsiz): {al_tut:.2f} kat")
        for yon in (("long",), ("long", "short")):
            print(f"  yön={'+'.join(yon)}")
            for L in (1, 2, 3, 5, 10, 20):
                r = kos(bar, L, yon)
                print(f"    {L:>2}x  son={r['son']:>9.2f} kat  yıllık={r['cagr']*100:>7.1f}%  "
                      f"en kötü düşüş={r['dd']*100:>7.1f}%  likidasyon={r['likit']}  işlem={r['islem']}")
