"""Spike C2: FOMC açıklaması tonu (Jev). Beklenen (görmeden yazıldı): 2022-06-15 → 5, 2020-03-15 → 1,
2012-09-13 → 1, 2015-12-16 → 4; karar: artış, indirim, sabit, artış."""
import html
import json
import re
import subprocess
import sys
import urllib.request

ORNEK = {"20220615": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20220615a.htm",
         "20200315": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm",
         "20120913": "https://www.federalreserve.gov/newsevents/press/monetary/20120913a.htm",
         "20151216": "https://www.federalreserve.gov/newsevents/press/monetary/20151216a.htm"}


def metin(url: str) -> str:
    h = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8", "ignore")
    m = re.search(r'id="article"(.*?)(<div[^>]*id="lastUpdate"|<footer)', h, re.S)
    g = m.group(1) if m else h
    g = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", g, flags=re.S)
    g = html.unescape(re.sub(r"<[^>]+>", " ", g))
    g = re.sub(r"\s+", " ", g).strip()
    g = re.sub(r"^.*?(Share|Release Date:[^.]*?(a\.m\.|p\.m\.) EDT|EST)", "", g, count=1)
    return g[:6000]


SORULAR = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "sorular.json", encoding="utf-8"))
for tarih, url in ORNEK.items():
    t = metin(url)
    istek = {"model": "jev-1.13.0", "state": {"aciklama": {"metin": t}}, "questions": SORULAR}
    json.dump(istek, open(f"istek_{tarih}.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("=====", tarih, len(t), "karakter:", t[:140].replace("\n", " "))
    r = subprocess.run([sys.executable, "C:/Users/scryn/Documents/ScryneOS/.claude/scripts/ts.py", "sor", "--json",
                        f"istek_{tarih}.json"], capture_output=True, text=True, encoding="utf-8")
    try:
        y = json.loads(r.stdout[r.stdout.index("{"):])
        for k, a in y["answers"].items():
            print(" ", k, {x: a.get(x) for x in ("choice", "score", "confidence")}, {p: round(v, 3) for p, v in (a.get("probabilities") or {}).items()} if k == "karar" else "")
    except Exception:
        print(r.stdout[-800:], r.stderr[-400:])
