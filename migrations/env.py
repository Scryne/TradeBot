"""Alembic ortamı: bağlantı adresi TradeBot ayarlarından (TRADEBOT_VERITABANI_URL) gelir, ini dosyasından değil."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from tradebot.ayar import ayarlar
from tradebot.db import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

a = ayarlar()
if a.veritabani_url is None:
    raise RuntimeError("TRADEBOT_VERITABANI_URL tanımlı değil")
config.set_main_option("sqlalchemy.url", a.veritabani_url.get_secret_value().replace("%", "%%"))
target_metadata = metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    baglanti_motoru = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                                         poolclass=pool.NullPool)
    with baglanti_motoru.connect() as baglanti:
        context.configure(connection=baglanti, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
