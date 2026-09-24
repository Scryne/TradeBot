import pytest

from tradebot.ayar import Ayarlar


@pytest.fixture
def ayar(tmp_path, monkeypatch):
    # Gerçek ortam değişkenleri ve .env testlere sızmasın
    for k in ("TYPESAFE_API_KEY", "NVIDIA_API_KEY", "TRADEBOT_TELEGRAM_TOKEN", "TRADEBOT_VERITABANI_URL"):
        monkeypatch.delenv(k, raising=False)
    return Ayarlar(_env_file=None, ortam="test", veri_dizini=tmp_path / "veri",
                   veritabani_url=f"sqlite:///{(tmp_path / 't.db').as_posix()}")
