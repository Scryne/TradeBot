"""Saf karar çekirdeği (değişmez kural 3).

Burada yalnız strateji mantığı durur: I/O yapmaz (dosya, ağ, veritabanı, saat yok), yalnız verilen geçmişe bakar.
Bir strateji fonksiyonu `Barlar` ve parametre alır, her bar için hedef ağırlık (sinyal) döndürür:
    out[t] ∈ [-1, 1], yalnız barlar[: t + 1]'e bağlıdır (bar t'nin KAPANIŞINDA verilen karar).
Yürütme (sonraki barın açılışında dolum), maliyet ve boyutlandırma çekirdeğin dışındadır.

Korumalar (tests/test_cekirdek.py):
- İzinli import listesi dışında modül kullanılamaz (AST taraması).
- Gelecek-bozma testi: t sonrası veri bozulunca out[: t + 1] değişmez.
"""
from tradebot.cekirdek.temel import Barlar, StratejiTanimi, nedensellik_testi

__all__ = ["Barlar", "StratejiTanimi", "nedensellik_testi"]
