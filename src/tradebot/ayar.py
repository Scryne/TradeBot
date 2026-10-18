"""Ayarlar ve sırlar. Tek kaynak: ortam değişkenleri (ve varsa `.env`).

Sırlar `SecretStr` tutulur: repr, log ve panoya düz metin olarak düşmez. Değerine yalnız kullanan kod
`.get_secret_value()` ile erişir. Sır listesi `SIR_ALANLARI`; log maskeleme bu listeyi kullanır.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SIR_ALANLARI = ("veritabani_url", "typesafe_api_key", "nvidia_api_key", "telegram_token", "binance_anahtar",
                "binance_gizli", "alpaca_anahtar", "alpaca_gizli")


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
    # Binance USDⓈ-M (Faz 12 gerçek kol): çekim izni kapalı, IP kısıtlı anahtar; yalnız host .env (kural 12)
    binance_anahtar: SecretStr | None = None
    binance_gizli: SecretStr | None = None
    # Alpaca PAPER hesabı (Nasdaq kolu): yalnız paper-api.alpaca.markets; canlı uç kodda yok (kural 7, gerçek para onayı)
    alpaca_anahtar: SecretStr | None = None
    alpaca_gizli: SecretStr | None = None
    telegram_sohbet: str | None = None    # Scryne'ın sohbet kimliği (sır değil; bot yalnız buraya yazar)
    yedek_dizini: Path | None = None      # compose `yedek`in hedefi; tanımlıysa sağlık yedek yaşını denetler
    olu_adam_url: str | None = None       # healthchecks.io ping adresi (yalnız .env'de): host kapanırsa dışarıdan alarm
    sessiz_saat_utc: tuple[int, int] = (19, 5)   # İstanbul 22:00–08:00 (UTC+3, yaz saati yok); KRITIK hariç biriktirilir
    # MT5 köprüleri (host Windows, tools/host/mt5kopru.ps1); tanımlıysa bekçi denetler
    mt5_kopru_forex: str | None = None
    mt5_kopru_viop: str | None = None

    # Sağlık eşikleri (Spike 02/03: bu evde DNS 5–15 sn, saat 1 sn kaymıştı)
    dns_uyari_sn: float = 1.0
    dns_hata_sn: float = 3.0
    saat_uyari_sn: float = 0.25
    saat_hata_sn: float = 0.5
    disk_uyari_gb: float = 50.0

    @field_validator(*SIR_ALANLARI, mode="before")
    @classmethod
    def _bos_sir_yok(cls, v):
        # `.env.example`'dan gelen `ANAHTAR=` satırları tanımsız sayılır (host'ta "tümü tanımlı" yanlış alarmı).
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    def sir_degerleri(self) -> list[str]:
        """Log maskeleme için tanımlı sırların düz değerleri (boş olmayanlar)."""
        out = []
        for ad in SIR_ALANLARI:
            v = getattr(self, ad)
            if v is not None and v.get_secret_value():
                out.append(v.get_secret_value())
        if self.olu_adam_url:   # ping adresi de gizlidir (adresi bilen sahte "ok" gönderebilir)
            out.append(self.olu_adam_url)
        return out


@lru_cache(maxsize=1)
def ayarlar() -> Ayarlar:
    return Ayarlar()
