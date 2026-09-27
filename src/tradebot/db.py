"""Veritabanı: bağlantı ve şema (SQLAlchemy Core). Göçler Alembic ile (`migrations/`).

Canlıda PostgreSQL, testte SQLite. JSON alanı PostgreSQL'de JSONB'dir.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from tradebot.ayar import Ayarlar

metadata = MetaData()
JSONT = JSON().with_variant(JSONB(), "postgresql")
# SQLite yalnız INTEGER PRIMARY KEY'i otomatik artırır
KIMLIK = BigInteger().with_variant(Integer(), "sqlite")

denetim_izi = Table(
    "denetim_izi",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("zaman", DateTime(timezone=True), nullable=False),
    Column("bilesen", String(64), nullable=False),
    Column("olay", String(128), nullable=False),
    Column("veri", JSONT, nullable=False),
    Column("onceki_hash", String(64), nullable=False),
    Column("hash", String(64), nullable=False, unique=True),
)

# --- Faz 2: veri platformu ---
ham_dosya = Table(
    "ham_dosya",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kaynak", String(32), nullable=False),
    Column("anahtar", String(256), nullable=False),  # kaynağa özgü mantıksal ad (ör. spot/1h/BTCUSDT/2024-01)
    Column("yol", String(512), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("boyut", BigInteger, nullable=False),
    Column("indirildi", DateTime(timezone=True), nullable=False),
    Index("ix_ham_dosya_kaynak_anahtar", "kaynak", "anahtar"),
    Index("ix_ham_dosya_sha256", "sha256"),
    UniqueConstraint("kaynak", "anahtar", "sha256", name="uq_ham_dosya"),
)

enstruman = Table(
    "enstruman",
    metadata,
    Column("kimlik", String(64), primary_key=True),  # "<PIYASA>:<SEMBOL>"
    Column("piyasa", String(32), nullable=False),
    Column("sembol", String(32), nullable=False),
    Column("sinif", String(16), nullable=False),  # kripto | fx | metal | endeks | emtia | etf | hisse
    Column("takvim", String(16), nullable=False),
    Column("para_birimi", String(8), nullable=False),
    Column("kaynak", String(32), nullable=False),
    Column("ilk_bar_ms", BigInteger),  # tarihsel evren: veride görülen ilk ve son bar (delist/listeleme)
    Column("son_bar_ms", BigInteger),
    Column("durum", String(16), nullable=False, default="aktif"),  # aktif | islem_disi
    Column("meta", JSONT, nullable=False, default=dict),  # fiyat adımı, lot, kaynak sembolü …
    Column("guncellendi", DateTime(timezone=True), nullable=False),
)

kurumsal_islem = Table(
    "kurumsal_islem",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kimlik", String(64), nullable=False),
    Column("tarih_ms", BigInteger, nullable=False),  # hak kullanım (ex) günü 00:00 UTC
    Column("tur", String(16), nullable=False),  # temettu | bolunme
    Column("deger", Float, nullable=False),  # temettü: pay başına tutar; bölünme: yeni/eski pay oranı
    Column("kaynak", String(32), nullable=False),
    Column("ham_sha", String(64), nullable=False),
    UniqueConstraint("kimlik", "tarih_ms", "tur", "kaynak", name="uq_kurumsal_islem"),
)

kalite_raporu = Table(
    "kalite_raporu",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("zaman", DateTime(timezone=True), nullable=False),
    Column("kimlik", String(64), nullable=False),
    Column("zaman_dilimi", String(8), nullable=False),
    Column("durum", String(8), nullable=False),  # OK | UYARI | HATA
    Column("ozet", JSONT, nullable=False),
    Index("ix_kalite_raporu_kimlik", "kimlik", "zaman_dilimi"),
)

# --- Faz 3: deneme defteri ---
test_plani = Table(
    "test_plani",
    metadata,
    Column("kimlik", String(128), primary_key=True),
    Column("zaman", DateTime(timezone=True), nullable=False),
    Column("aile", String(64), nullable=False),
    Column("hipotez", String(2000), nullable=False),
    Column("izgara", JSONT, nullable=False),
    Column("piyasalar", JSONT, nullable=False),
    Column("olcut", String(2000), nullable=False),
    Column("kod_surumu", String(64), nullable=False),
    Column("durum", String(16), nullable=False),  # acik | kapandi
    Column("sonuc", String(4000)),
)

deneme = Table(
    "deneme",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("zaman", DateTime(timezone=True), nullable=False),
    Column("plan", String(128), nullable=False),
    Column("tur", String(16), nullable=False),  # tarama | walk_forward | nautilus | paper
    Column("strateji", String(256), nullable=False),
    Column("aile", String(64), nullable=False),
    Column("parametreler", JSONT, nullable=False),
    Column("enstruman", String(64), nullable=False),
    Column("zaman_dilimi", String(8), nullable=False),
    Column("veri_hash", String(64), nullable=False),
    Column("kod_surumu", String(64), nullable=False),
    Column("metrik", JSONT, nullable=False),
    Column("sure_sn", Float, nullable=False),
    Index("ix_deneme_aile_tur", "aile", "tur"),
    Index("ix_deneme_plan", "plan"),
)


# --- Faz 6: zekâ katmanı ---
metin = Table(
    "metin",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kaynak", String(32), nullable=False),        # binance_duyuru | kap | sec | rss:<ad> …
    Column("dis_kimlik", String(128), nullable=False),   # kaynağın kimliği (Binance articleCode, KAP bildirim no …)
    Column("katalog", String(64)),
    Column("baslik", String(1000), nullable=False),
    Column("govde", Text, nullable=False),
    Column("yayin_ms", BigInteger, nullable=False),      # kaynağın beyan ettiği İLK yayın zamanı (kural 9)
    Column("ilk_gorulme_ms", BigInteger, nullable=False),  # bizim ilk gördüğümüz an (canlı gecikme ölçümü)
    Column("ham_sha", String(64), nullable=False),       # ham yanıtın hash'i (ham_dosya)
    Column("meta", JSONT),                               # kaynağa özgü (KAP: hisseler, konu, sınıf)
    UniqueConstraint("kaynak", "dis_kimlik", name="uq_metin"),
    Index("ix_metin_yayin", "yayin_ms"),
)

jev_yargi = Table(
    "jev_yargi",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("zaman", DateTime(timezone=True), nullable=False),
    Column("rol", String(32), nullable=False),           # A1_binance, …
    Column("saglayici", String(16), nullable=False),     # jev | nvidia
    Column("model_istenen", String(128), nullable=False),
    Column("model_cozulen", String(128)),
    Column("soru_sha", String(64), nullable=False),      # soru tanımlarının hash'i (dondurma anahtarı)
    Column("girdi_sha", String(64), nullable=False),     # state'in hash'i
    Column("hedef", String(256), nullable=False),        # ör. metin:42|BINANCE:ICXUSDT
    Column("cevap", JSONT),                              # {soru: {choice, confidence, probabilities} …}
    Column("gecikme_ms", Float),
    Column("girdi_token", Integer),
    Column("hata", String(500)),
    Index("ix_jev_yargi_anahtar", "soru_sha", "girdi_sha"),
)

olay = Table(
    "olay",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("zaman", DateTime(timezone=True), nullable=False),
    Column("tur", String(16), nullable=False),           # veto | uyari
    Column("enstruman", String(64), nullable=False),
    Column("gecerli_ms", BigInteger, nullable=False),    # olayın motora/backtest'e görünür olduğu an (yayın + gecikme)
    Column("bitis_ms", BigInteger),                      # boş: süresiz (ör. delist)
    Column("neden", String(500), nullable=False),
    Column("rol", String(32), nullable=False),
    Column("metin_id", BigInteger),
    Column("yargi_id", BigInteger),
    Column("ayrinti", JSONT, nullable=False),
    Index("ix_olay_enstruman", "enstruman", "gecerli_ms"),
)

# --- Faz 7: paper defteri (hepsi yalnız eklenir; kol durumu bu kayıtlardan yeniden kurulur) ---
paper_kol = Table(
    "paper_kol",
    metadata,
    Column("kol", String(96), primary_key=True),
    Column("acilis", DateTime(timezone=True), nullable=False),
    Column("baslangic_ms", BigInteger, nullable=False),
    Column("baslangic_ozkaynak", Float, nullable=False),
    Column("sinif", String(8), nullable=False),          # B (sermayesiz gözlem) | A (sermayeli)
    Column("tanim", JSONT, nullable=False),              # config/paper.yaml satırı (strateji, parametre, boyut, jev)
    Column("kod_surumu", String(64), nullable=False),
)

paper_karar = Table(
    "paper_karar",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kol", String(96), nullable=False),
    Column("bar_ms", BigInteger, nullable=False),        # kararın dayandığı son kapanmış barın açılışı
    Column("karar_ms", BigInteger, nullable=False),      # duvar saati: emirden ÖNCE yazıldığının kanıtı
    Column("kod_surumu", String(64), nullable=False),
    Column("veri_hash", String(64), nullable=False),
    Column("durum", String(16), nullable=False),         # normal | fren_* | acil_durdurma
    Column("ayrinti", JSONT, nullable=False),            # kimlikler, hedef, etkin, kaymis, yeni, fiyat, veto, miktar
    UniqueConstraint("kol", "bar_ms", name="uq_paper_karar"),
)

paper_emir = Table(
    "paper_emir",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kol", String(96), nullable=False),
    Column("karar_id", BigInteger),                      # toparlanma emrinde boş
    Column("istemci_emir_id", String(64), nullable=False, unique=True),
    Column("enstruman", String(64), nullable=False),
    Column("istenen", Float, nullable=False),            # işaretli adet
    Column("onaylanan", Float, nullable=False),          # risk motorundan sonra (0 = ret)
    Column("karar_fiyati", Float, nullable=False),       # son kapanış (kayma ölçümü için)
    Column("gonderim_fiyati", Float),                    # emir giderken canlı orta fiyat (göç 0008; öncesi boş)
    Column("zaman_ms", BigInteger, nullable=False),
    Column("tur", String(16), nullable=False),           # karar | toparlanma
    Column("risk", JSONT, nullable=False),               # {onay, gerekceler, risk_azaltan}
)

paper_emir_olay = Table(
    "paper_emir_olay",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("emir_id", BigInteger, nullable=False),
    Column("kol", String(96), nullable=False),
    Column("tur", String(16), nullable=False),           # dolum | ret | iptal
    Column("enstruman", String(64), nullable=False),
    Column("miktar", Float, nullable=False),             # dolumda işaretli adet
    Column("fiyat", Float),
    Column("ucret", Float, nullable=False),              # kote para (USDT)
    Column("zaman_ms", BigInteger, nullable=False),
    Column("ayrinti", JSONT, nullable=False),
    Index("ix_paper_emir_olay_kol", "kol", "zaman_ms"),
)

paper_ozkaynak = Table(
    "paper_ozkaynak",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kol", String(96), nullable=False),
    Column("zaman_ms", BigInteger, nullable=False),
    Column("ozkaynak", Float, nullable=False),
    Column("nakit", Float, nullable=False),
    Column("pozisyon", JSONT, nullable=False),           # {enstrüman: adet}
    Column("fiyat", JSONT, nullable=False),              # {enstrüman: işaret fiyatı}
    Index("ix_paper_ozkaynak_kol", "kol", "zaman_ms"),
)

paper_kol_olay = Table(  # kolun durum olayları (yalnız eklenir): durdur | acil_kaldir | terfi
    "paper_kol_olay",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kol", String(96), nullable=False),
    Column("zaman_ms", BigInteger, nullable=False),
    Column("tur", String(16), nullable=False),
    Column("kod_surumu", String(64), nullable=False),
    Column("ayrinti", JSONT, nullable=False),            # acil_kaldir: onaylayan, gerekce · terfi: eski, yeni, gerekce
    Index("ix_paper_kol_olay_kol", "kol", "zaman_ms"),
)

paper_dagitim = Table(  # haftalık sermaye dağıtımı (canli/dagitici.py); yalnız eklenir, hafta başına bir kayıt
    "paper_dagitim",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("portfoy", String(96), nullable=False),       # portföy kolunun adı
    Column("hafta_ms", BigInteger, nullable=False),      # Pazartesi 00:00 UTC; girdi bundan önceki veridir
    Column("hesap_ms", BigInteger, nullable=False),      # duvar saati
    Column("kod_surumu", String(64), nullable=False),
    Column("kaldirac", Float, nullable=False),           # Σ katsayı (dağıtılan)
    Column("ayrinti", JSONT, nullable=False),            # kol başına σ, Sharpe, ERC, eğim, ağırlık, kademe, katsayı
    UniqueConstraint("portfoy", "hafta_ms", name="uq_paper_dagitim"),
)


def motor(a: Ayarlar) -> Engine:
    if a.veritabani_url is None:
        raise RuntimeError("TRADEBOT_VERITABANI_URL tanımlı değil")
    return create_engine(a.veritabani_url.get_secret_value(), pool_pre_ping=True, future=True)
