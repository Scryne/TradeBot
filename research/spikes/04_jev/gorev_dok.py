"""Spike 04-B hazırlık: 90 etiketli örneği (Binance A1 + KAP A2) yükseltme modeli testi için tek dosyaya döker.
Tanımlar spike 04-A'daki Choice'lardan (aynı soru), Jev cevapları 04-A sonuç dosyalarından gelir."""
import json
from pathlib import Path

import veto_binance as vb
import veto_kap as vk

D = Path(__file__).parent / "data"
out = []
sb = json.load(open(D / "binance_secki.json", encoding="utf-8"))
jb = {(k["i"], k["varlik"]): k for k in json.load(open(D / "veto_binance_sonuc.json", encoding="utf-8"))["kayit"]}
for e in vb.ETIKET:
    i, varlik, altin = e[:3]
    kabul = sorted(e[3] if len(e) > 3 else {altin})
    d = sb[i]
    j = jb[(i, varlik)]
    out.append({"set": "binance", "id": f"b{i}-{varlik}", "altin": altin, "kabul": kabul, "veto": sorted(vb.VETO),
                "state": {"duyuru": {"baslik": d["baslik"], "metin": d["govde"][:4000]}, "varlik": varlik},
                "jev": j["jev"], "jev_guven": j["guven"]})
sk = json.load(open(D / "kap_secki.json", encoding="utf-8"))
jk = {k["i"]: k for k in json.load(open(D / "veto_kap_sonuc.json", encoding="utf-8"))["kayit"]}
for i, (altin, kabul) in vk.ETIKET.items():
    b = sk[i]
    j = jk[i]
    out.append({"set": "kap", "id": f"k{i}-{b['sembol']}", "altin": altin, "kabul": sorted(kabul or {altin}),
                "veto": sorted(vk.VETO), "tuzak": vk.TUZAK.get(i),
                "state": {"sembol": b["sembol"], "bildirim": {"baslik": b["baslik"], "metin": b["govde"][:4000]}},
                "jev": j["jev"], "jev_guven": j["guven"]})
tanim = {"binance": vb.ETKI.model_dump(mode="json"), "kap": vk.ETKI.model_dump(mode="json")}
json.dump({"tanim": tanim, "ornekler": out}, open(D / "yukseltme_gorevler.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(len(out), "örnek", {s: sum(o["set"] == s for o in out) for s in ("binance", "kap")})
