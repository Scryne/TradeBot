"""Rollerin ortak veto kuralı (saf fonksiyon: politika kodda, model yalnız metni yorumlar; kural 8).

- Jev seçimi ve güven ≥ eşik → seçim veto kümesindeyse veto.
- Güven < eşik → yükseltme modelinin cevabı veto kümesindeyse veto.
- Yükseltme yoksa ya da başarısızsa: Jev'in kendi seçimi ya da en olası iki seçeneğinden biri veto kümesindeyse veto +
  uyarı (belirsizlikte riski azalt). Spike 04-B: bu kural yükseltmesiz 60 belirsiz vakada 8 yanlış veto verdi, yükseltme 0.
- Hiç bilgi yoksa (seçim ve olasılık yok, yükseltme yok): veto (2026-10-18 denetimi: eskiden "uyarı var, veto yok"du;
  bilinmeyen durumda izin veren varsayılan kural 8'e aykırı).
"""
from __future__ import annotations


def karar(secim: str | None, guven: float, olasiliklar: dict, yukseltme: str | None, yukseltme_denendi: bool,
          veto_kumesi: set[str], esik: float = 0.5) -> tuple[bool, str]:
    """(veto mu, gerekçe)."""
    if secim is not None and guven >= esik:
        return secim in veto_kumesi, f"jev:{secim} ({guven:.2f})"
    if yukseltme is not None:
        return yukseltme in veto_kumesi, f"yukseltme:{yukseltme} (jev {secim} {guven:.2f})"
    ilk_iki = sorted(olasiliklar.items(), key=lambda kv: -kv[1])[:2]
    adaylar = [k for k, _ in ilk_iki] + ([secim] if secim is not None else [])
    belirsiz_veto = not adaylar or any(k in veto_kumesi for k in adaylar)
    neden = "yukseltme_basarisiz" if yukseltme_denendi else "yukseltme_yok"
    return belirsiz_veto, f"belirsiz:{secim} ({guven:.2f}), {neden}, ilk iki {[k for k, _ in ilk_iki]}"
