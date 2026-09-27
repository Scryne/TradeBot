"""Haber takvimi ayrıştırma (FOMC, BLS arşivleri)."""
from tradebot.veri import haber_takvimi as ht


def test_haber_takvimi_ayristirma():
    fomc = '<a href="/newsevents/pressreleases/monetary20250917a.htm">HTML</a> monetary20250917a1.htm'
    nfp = ('<a href="/news.release/archives/empsit_09052025.htm">Aug</a>'
           '<a href="/news.release/archives/empsit_11202025.htm">Sep</a> archives/empsit_11202025.pdf')
    assert ht.fomc_tarihleri(fomc) == ["20250917"]  # a1 (uygulama notu) değil, karar metni
    assert ht.bls_tarihleri(nfp, "empsit") == ["20250905", "20251120"]
    ol = ht.olaylar(fomc, nfp, "")
    # yaz saati: 17 Eylül 2025 14:00 EDT = 18:00 UTC; 20 Kasım 2025 08:30 EST = 13:30 UTC
    assert [(o["olay"], o["utc_ms"]) for o in ol] == [
        ("NFP", 1757075400000), ("FOMC", 1758132000000), ("NFP", 1763645400000)]
