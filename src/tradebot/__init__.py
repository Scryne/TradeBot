"""TradeBot — Scryne'ın kendi hesabı için kurumsal, çok piyasalı, otonom trade sistemi."""

__version__ = "0.1.0"


def main() -> None:
    from tradebot.cli import uygulama

    uygulama()
