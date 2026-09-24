import json
import logging

from tradebot.ayar import Ayarlar
from tradebot.kayit import MASKE, kur, log, sir_maskeleyici


def test_sir_repr_ve_dumpta_gorunmez(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "gizli-anahtar-123456")
    a = Ayarlar(_env_file=None)
    assert "gizli-anahtar-123456" not in repr(a)
    assert "gizli-anahtar-123456" not in a.model_dump_json()
    assert a.typesafe_api_key.get_secret_value() == "gizli-anahtar-123456"


def test_maskeleyici_ad_ve_deger():
    m = sir_maskeleyici(["s3cr3t-degeri", "postgresql://u:parola123@db/x"])
    olay = m(None, None, {
        "event": "baglanti hatasi: postgresql://u:parola123@db/x reddetti",
        "api_key": "herhangi",
        "ic": {"authorization": "Bearer x", "not": "anahtar s3cr3t-degeri burada"},
        "liste": ["s3cr3t-degeri", 5],
    })
    metin = json.dumps(olay)
    assert "parola123" not in metin and "s3cr3t-degeri" not in metin
    assert olay["api_key"] == MASKE and olay["ic"]["authorization"] == MASKE
    assert olay["liste"][0] == MASKE and olay["liste"][1] == 5


def test_log_satiri_json_ve_maskeli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-cokgizli-9999")
    a = Ayarlar(_env_file=None, log_dizini=tmp_path)
    kur(a)
    log("test").warning("deneme", ayrinti="anahtar nvapi-cokgizli-9999 kullanildi")
    logging.shutdown()
    satir = (tmp_path / "tradebot.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    kayit = json.loads(satir)
    assert kayit["bilesen"] == "test" and kayit["level"] == "warning"
    assert kayit["zaman"].endswith("Z")  # UTC
    assert "nvapi-cokgizli-9999" not in satir
