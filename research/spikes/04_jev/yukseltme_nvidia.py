"""Spike 04-B: belirsiz durumda yükseltme modeli (NVIDIA build, OpenAI uyumlu). Host'ta çalışır (anahtar host'ta).

Aynı 90 etiketli örnek (Binance A1 46 + KAP A2 44), Jev'e sorulan tanımların aynısı. Model JSON döndürür:
{"etki": "<seçenek>"}. Ölçülen: kabul kümesine göre doğruluk, veto yanlış alarm/kaçırılan, gecikme, JSON uyumu.
Kullanım (host konteynerinde): python yukseltme_nvidia.py gorevler.json sonuc.json model1 model2 ...
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time

import httpx

URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def istem(tanim: dict, state: dict) -> list[dict]:
    secenekler = "\n".join(f"- {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in tanim["criteria"].items())
    return [
        {"role": "system", "content": "You are a precise classifier. Read the task, the options and the input, then answer "
                                      "with a single JSON object and nothing else."},
        {"role": "user", "content": f"TASK:\n{json.dumps(tanim['instructions'], ensure_ascii=False)}\n\n"
                                    f"OPTIONS (choose exactly one key):\n{secenekler}\n\n"
                                    f"INPUT (JSON; backticked names in the task refer to these fields):\n"
                                    f"{json.dumps(state, ensure_ascii=False)}\n\n"
                                    'Answer format: {"etki": "<one option key>"}'},
    ]


def coz(metin: str, anahtarlar: set[str]) -> str | None:
    metin = re.sub(r"<think>.*?</think>", "", metin or "", flags=re.S)
    for m in reversed(re.findall(r"\{[^{}]*\}", metin)):
        try:
            v = json.loads(m).get("etki")
        except (json.JSONDecodeError, AttributeError):
            continue
        if v in anahtarlar:
            return v
    return None


def sor(c: httpx.Client, anahtar: str, model: str, mesajlar: list[dict]) -> tuple[str, float, dict]:
    for deneme in range(6):
        t0 = time.perf_counter()
        r = c.post(URL, headers={"Authorization": f"Bearer {anahtar}"},
                   json={"model": model, "messages": mesajlar, "temperature": 0, "max_tokens": 4096})
        sure = time.perf_counter() - t0
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * 2**deneme)
            continue
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"].get("content") or "", sure, j.get("usage", {})
    raise RuntimeError(f"{model}: tekrar denemeler tükendi")


def main() -> None:
    from tradebot.ayar import ayarlar

    gorev_yol, sonuc_yol, *modeller = sys.argv[1:]
    g = json.load(open(gorev_yol, encoding="utf-8"))
    anahtar = ayarlar().nvidia_api_key.get_secret_value()
    sonuc = []
    with httpx.Client(timeout=180) as c:
        for model in modeller:
            for o in g["ornekler"]:
                tanim = g["tanim"][o["set"]]
                try:
                    cevap, sure, kullanim = sor(c, anahtar, model, istem(tanim, o["state"]))
                    etki = coz(cevap, set(tanim["criteria"]))
                    hata = None
                except Exception as e:  # noqa: BLE001 — spike: hatayı kaydet, devam et
                    etki, sure, kullanim, hata = None, float("nan"), {}, str(e)[:200]
                sonuc.append({"model": model, "id": o["id"], "set": o["set"], "altin": o["altin"], "kabul": o["kabul"],
                              "etki": etki, "dogru": etki in o["kabul"], "sure": sure, "hata": hata,
                              "veto_altin": o["altin"] in o["veto"], "veto_model": etki in o["veto"],
                              "jev": o["jev"], "jev_guven": o["jev_guven"], "tuzak": o.get("tuzak"),
                              "cikti_token": kullanim.get("completion_tokens")})
                time.sleep(1.5)
            s = [x for x in sonuc if x["model"] == model]
            dogru = sum(x["dogru"] for x in s)
            fp = sum(x["veto_model"] and not x["veto_altin"] for x in s)
            fn = sum(x["veto_altin"] and not x["veto_model"] for x in s)
            sureler = sorted(x["sure"] for x in s if x["sure"] == x["sure"])
            med = statistics.median(sureler) if sureler else float("nan")
            p90 = sureler[int(len(sureler) * 0.9)] if sureler else float("nan")
            print(f"{model:<42} doğru {dogru}/{len(s)}  JSON yok {sum(x['etki'] is None for x in s)}  "
                  f"yanlış veto {fp}  kaçırılan {fn}  gecikme medyan {med:.1f} sn  p90 {p90:.1f} sn", flush=True)
            json.dump(sonuc, open(sonuc_yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
