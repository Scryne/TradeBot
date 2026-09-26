"""Faz 6: A2 üretim metin biçimi (tradebot.metin.kap) Spike 04-A'nın 44 KAP örneğinde doğruluğu koruyor mu?

Aynı bildirimler KAP'tan yeniden indirilir, gövde üretim ayıklayıcısıyla (`sayfa_govdesi`) çıkarılır, başlık üretimdeki
gibi "konu: özet" kurulur. Jev aynı soruyla (a2_kap.SORULAR) sorulur, altın etiketlerle karşılaştırılır.
Kullanım (proje kökünden): uv run python research/spikes/04_jev/a2_bicim_dogrula.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from typesafe_sdk import TypeSafeClient

from tradebot.metin import kap
from tradebot.veri.http import NazikIstemci
from tradebot.zeka import a2_kap as a2

sys.stdout.reconfigure(encoding="utf-8")
D = Path(__file__).parent / "data"
sys.path.insert(0, str(Path(__file__).parent))
import veto_kap as vk  # noqa: E402

sec = json.load(open(D / "kap_secki.json", encoding="utf-8"))
h = NazikIstemci("kap", aralik_sn=0.5, basliklar={"User-Agent": "Mozilla/5.0", "Accept-Language": "tr"})
c = TypeSafeClient()
kayit = []
for i, (altin, kabul) in vk.ETIKET.items():
    kabul = kabul or {altin}
    b = sec[i]
    sayfa = h.al(kap.SAYFA.format(b["id"])).decode("utf-8", "ignore")
    akis = "".join(json.loads('"' + m.group(1) + '"') for m in kap._AKIS.finditer(sayfa))
    ozet = (re.search(r'"summary":"((?:[^"\\]|\\.)*)"', akis) or [None, ""])[1]
    konu = (re.search(r'"disclosureBasic":\{"title":"((?:[^"\\]|\\.)*)"', akis) or [None, b["baslik"]])[1]
    govde = kap.sayfa_govdesi(sayfa)
    baslik = f"{konu}: {ozet}" if ozet and ozet != konu else konu
    metin_ = f"Özet Bilgi: {ozet}\n{govde}" if govde else ozet
    st = {"sembol": b["sembol"], "bildirim": {"baslik": baslik, "metin": metin_[:4000]}}
    r = c.system_one(st, a2.SORULAR, model="jev-1.13.0")
    e = r.choices["etki"]
    kayit.append({"i": i, "id": b["id"], "altin": altin, "kabul": sorted(kabul), "jev": e.choice, "guven": round(e.confidence, 3),
                  "dogru": e.choice in kabul, "veto_altin": altin in a2.VETO, "veto_jev": e.choice in a2.VETO,
                  "govde_uzunluk": len(govde)})
    k = kayit[-1]
    print(f"{'✓' if k['dogru'] else '✗'} #{i:<2} {b['sembol']:<6} altın={altin:<16} jev={e.choice:<16} güven={e.confidence:.2f} "
          f"gövde={len(govde)}")
json.dump(kayit, open(D / "a2_bicim_sonuc.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
n = len(kayit)
fp = sum(k["veto_jev"] and not k["veto_altin"] for k in kayit)
fn = sum(k["veto_altin"] and not k["veto_jev"] for k in kayit)
print(f"\ndoğru {sum(k['dogru'] for k in kayit)}/{n} · yanlış veto {fp} · kaçırılan {fn} · "
      f"güven<0,5 {sum(k['guven'] < 0.5 for k in kayit)} · boş gövde {sum(k['govde_uzunluk'] == 0 for k in kayit)}")
