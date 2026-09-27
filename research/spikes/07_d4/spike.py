"""Spike D4: Telegram doğal dil → komut + kol (Jev). Beklentiler sonuca bakmadan yazıldı."""
import json, subprocess, sys

KOLLAR = {
 "ma_yon@kripto_btc_eth@1h": "ma_yon (moving-average direction trend) arm, 1-hour bars, BTC+ETH, without Jev veto",
 "ma_yon@kripto_btc_eth@1h+jev": "ma_yon (moving-average direction trend) arm, 1-hour bars, BTC+ETH, with Jev veto",
 "tsmom@kripto_btc_eth@4h": "tsmom (time-series momentum) arm, 4-hour bars, wave 1, without Jev veto",
 "d2:tsmom@kripto_btc_eth@4h": "tsmom (time-series momentum) arm, 4-hour bars, wave 2 (slow volatility), without Jev veto",
 "d2:donchian_ls@kripto_btc_eth@1d": "donchian breakout arm, daily bars, wave 2, without Jev veto",
 "agresif@kripto_btc_eth": "aggressive observation arm (full Kelly)",
 "portfoy@kripto_btc_eth": "portfolio arm run by the capital allocator",
}
KOMUT = {"type": "choice", "instructions": {
  "what": "The message in `mesaj` is from the owner of an automated paper-trading system, sent to its Telegram bot. What is the owner asking the bot to do?",
  "not_for": "The bot never predicts prices or gives trading advice, and never increases risk from a free-text message."},
 "criteria": {
  "ozet": "Show the overall status: whether the system is healthy and how the paper arms are doing in total.",
  "kol_durumu": "Show the performance, equity or positions of one arm or of all arms.",
  "dagitim": "Show the capital allocator's weekly allocation, weights or leverage.",
  "vetolar": "Show the currently active Jev vetoes or news/announcement blocks on instruments.",
  "rapor": "Show the latest weekly paper report.",
  "kol_durdur": "Stop one specific arm from taking new risk.",
  "tumunu_durdur": "Stop all arms / the whole system from taking new risk.",
  "riski_artir": "Resume, restart, un-stop or unfreeze something, lift a stop or veto, raise leverage, or open/increase a position.",
  "yardim": "Ask what the bot can do or how to use it.",
  "bilinmiyor": {"what": "Anything else, including asking for price predictions, market direction or trading advice, or small talk."}}}
KOL = {"type": "choice", "instructions": "Which paper-trading arm does the message in `mesaj` refer to? Use `kollar` for the arms' descriptions.",
 "criteria": {**{k: v for k, v in KOLLAR.items()}, "hepsi": "All arms, or no specific arm is named."}}

ORNEK = [  # (mesaj, beklenen komut, beklenen kol)
 ("sistem sağlıklı mı?", "ozet", "hepsi"),
 ("bu hafta ne kazandık", "ozet|rapor|kol_durumu", "hepsi"),
 ("agresif kol nasıl gidiyor", "kol_durumu", "agresif@kripto_btc_eth"),
 ("jevli ma yön kolunun pozisyonu ne", "kol_durumu", "ma_yon@kripto_btc_eth@1h+jev"),
 ("dağıtım ne durumda, kaldıraç kaç", "dagitim", "hepsi"),
 ("aktif veto var mı", "vetolar", "hepsi"),
 ("BTC yarın yükselir mi sence", "bilinmiyor", "hepsi"),
 ("her şeyi durdur hemen", "tumunu_durdur", "hepsi"),
 ("donchian günlük kolu durdur", "kol_durdur", "d2:donchian_ls@kripto_btc_eth@1d"),
 ("portföyü tekrar başlat", "riski_artir", "portfoy@kripto_btc_eth"),
 ("kaldıracı 3x yap", "riski_artir", "hepsi"),
 ("neler yapabiliyorsun", "yardim", "hepsi"),
]
dogru = 0
for mesaj, bk, bkol in ORNEK:
    istek = {"model": "jev-1.13.0", "state": {"mesaj": mesaj, "kollar": KOLLAR}, "questions": {"komut": KOMUT, "kol": KOL}}
    json.dump(istek, open("istek.json", "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run([sys.executable, "C:/Users/scryn/Documents/ScryneOS/.claude/scripts/ts.py", "sor", "--json", "istek.json"],
                       capture_output=True, text=True, encoding="utf-8")
    y = json.loads(r.stdout[r.stdout.index("{"):])["answers"]
    k, kc, ko, koc = y["komut"]["choice"], y["komut"]["confidence"], y["kol"]["choice"], y["kol"]["confidence"]
    ok = k in bk.split("|") and (ko == bkol or bk in ("ozet", "dagitim", "vetolar", "yardim", "bilinmiyor", "tumunu_durdur", "ozet|rapor|kol_durumu"))
    dogru += ok
    print(f"{'✓' if ok else '✗'} {mesaj!r:40} komut={k} ({kc:.2f}) kol={ko} ({koc:.2f})  beklenen={bk}/{bkol}")
print("dogru", dogru, "/", len(ORNEK))
