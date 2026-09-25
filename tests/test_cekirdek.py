import ast
from pathlib import Path

import numpy as np
import pytest

from tradebot.cekirdek import Barlar, StratejiTanimi, nedensellik_testi, ornek
from tradebot.cekirdek.gosterge import kayan_max, sma

CEKIRDEK = Path(__file__).resolve().parents[1] / "src" / "tradebot" / "cekirdek"
IZINLI = {"__future__", "numpy", "math", "dataclasses", "typing", "collections", "functools", "itertools",
          "numpy.lib.stride_tricks", "collections.abc"}


def barlar(n=600, tohum=1):
    rng = np.random.default_rng(tohum)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    o = np.r_[c[0], c[:-1]]
    return Barlar(np.arange(n, dtype=np.int64) * 3_600_000, o, np.maximum(o, c) * 1.01, np.minimum(o, c) * 0.99, c,
                  rng.uniform(1, 10, n))


YASAK_CAGRI = {"open", "exec", "eval", "__import__", "input", "print"}


def io_ihlalleri(kaynak: str) -> list[str]:
    out = []
    for dugum in ast.walk(ast.parse(kaynak)):
        if isinstance(dugum, ast.Import | ast.ImportFrom):
            adlar = [a.name for a in dugum.names] if isinstance(dugum, ast.Import) else [dugum.module or ""]
            out += [f"import {a}" for a in adlar if a not in IZINLI and not a.startswith("tradebot.cekirdek")]
        elif isinstance(dugum, ast.Call) and getattr(dugum.func, "id", "") in YASAK_CAGRI:
            out.append(f"{dugum.func.id}() çağrısı")
    return out


def test_cekirdek_io_yapamaz():
    """Çekirdek yalnız izinli modülleri import edebilir; dosya/çalıştırma çağrısı yapamaz."""
    for dosya in CEKIRDEK.glob("*.py"):
        assert io_ihlalleri(dosya.read_text(encoding="utf-8")) == [], dosya.name


def test_io_denetimi_ihlali_yakalar():
    kotu = "import os\nfrom pathlib import Path\nimport httpx\nx = open('a')\n"
    assert io_ihlalleri(kotu) == ["import os", "import pathlib", "import httpx", "open() çağrısı"]


@pytest.mark.parametrize("tanim", [
    StratejiTanimi("sma", "trend", ornek.sma_kesisim, {"hizli": 10, "yavas": 50}),
    StratejiTanimi("donchian", "kirilim", ornek.donchian, {"giris": 20, "cikis": 10}),
    StratejiTanimi("tsmom", "trend", ornek.tsmom, {"ufuk": 40, "hedef_vol": 0.01}, yon="long_short"),
])
def test_ornek_stratejiler_gelecegi_gormez(tanim):
    nedensellik_testi(tanim, barlar())


def test_nedensellik_testi_hileyi_yakalar():
    def hileli(b):  # yarının kapanışına bakıyor
        return np.r_[(b.close[1:] > b.close[:-1]).astype(float), 0.0]
    with pytest.raises(AssertionError, match="geleceği görüyor"):
        nedensellik_testi(StratejiTanimi("hile", "test", hileli), barlar())


def test_gostergeler():
    x = np.arange(1.0, 11.0)
    assert np.isnan(sma(x, 3)[1]) and sma(x, 3)[2] == 2.0 and sma(x, 3)[-1] == 9.0
    m = kayan_max(x, 3)
    assert np.isnan(m[2]) and m[3] == 3.0 and m[-1] == 9.0  # t hariç önceki 3 bar


def test_sinyal_kirpma_ve_yon():
    b = barlar(200)
    ls = StratejiTanimi("t", "trend", ornek.tsmom, {"ufuk": 20}, yon="long_short").sinyal(b)
    lo = StratejiTanimi("t", "trend", ornek.tsmom, {"ufuk": 20}).sinyal(b)
    assert ls.min() < 0 and lo.min() >= 0 and set(np.unique(lo)) <= {0.0, 1.0}


def test_kimlik_deterministik():
    a = StratejiTanimi("sma", "trend", ornek.sma_kesisim, {"yavas": 50, "hizli": 10})
    assert a.kimlik() == "trend/sma(hizli=10,yavas=50)"
