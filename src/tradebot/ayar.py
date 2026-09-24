"""Ayarlar ve sırlar. Tek kaynak: ortam değişkenleri (ve varsa `.env`).

Sırlar `SecretStr` tutulur: repr, log ve panoya düz metin olarak düşmez. Değerine yalnız kullanan kod
`.get_secret_value()` ile erişir. Sır listesi `SIR_ALANLARI`; log maskeleme bu listeyi kullanır.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SIR_ALANLARI = ("veritabani_url", "typesafe_api_key", "nvidia_api_key", "telegram_token")


class Ayarlar(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADEBOT_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ortam: Literal["gelistirme", "host", "test"] = "gelistirme"
    log_seviyesi: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_dizini: Path | None = None
    veri_dizini: Path = Path("data")

    veritabani_url: SecretStr | None = None

    # Dış servis anahtarları kendi yerleşik adlarıyla okunur (TypeSafe SDK da aynı adı kullanır).
    typesafe_api_key: SecretStr | None = Field(default=None, validation_alias="TYPESAFE_API_KEY")
    nvidia_api_key: SecretStr | None = Field(default=None, validation_alias="NVIDIA_API_KEY")
    telegram_token: SecretStr | None = Field(default=None, validation_alias="TRADEBOT_TELEGRAM_TOKEN")

    # Sağlık eşikleri (Spike 02/03: bu evde DNS 5–15 sn, saat 1 sn kaymıştı)
    dns_uyari_sn: float = 1.0
    dns_hata_sn: float = 3.0
    saat_uyari_sn: float = 0.25
    saat_hata_sn: float = 0.5
    disk_uyari_gb: float = 50.0

    def sir_degerleri(self) -> list[str]:
        """Log maskeleme için tanımlı sırların düz değerleri (boş olmayanlar)."""
        out = []
        for ad in SIR_ALANLARI:
            v = getattr(self, ad)
            if v is not None and v.get_secret_value():
                out.append(v.get_secret_value())
        return out


@lru_cache(maxsize=1)
def ayarlar() -> Ayarlar:
    return Ayarlar()
