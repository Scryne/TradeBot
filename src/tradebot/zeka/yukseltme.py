"""Yükseltme modeli: Jev'in güveni eşiğin altındayken aynı soruyu OpenAI uyumlu bir sohbet modeline sorar
(varsayılan NVIDIA build; sağlayıcıdan bağımsız: base_url + model listesi config/zeka.yaml'da).

- Aynı seçenek tanımları (Choice `criteria`) ve aynı girdi; model yalnız seçenek anahtarı döndürür (JSON).
- Yedek zinciri: listedeki modeller sırayla denenir; ilk geçerli cevap kullanılır.
- Her deneme `jev_yargi`'ya yazılır (saglayici = "nvidia", model_istenen = model adı).
- Hepsi başarısızsa None: çağıran "riski azalt + alarm" kuralını uygular (kural 8).
"""
from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import insert
from sqlalchemy.engine import Engine

from tradebot.db import jev_yargi
from tradebot.kayit import log
from tradebot.zeka.jev import kanonik_sha

_log = log("zeka.yukseltme")


def istem(tanim: dict, state: dict, alan: str) -> list[dict]:
    secenekler = "\n".join(f"- {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in tanim["criteria"].items())
    return [
        {"role": "system", "content": "You are a precise classifier. Read the task, the options and the input, then answer "
                                      "with a single JSON object and nothing else."},
        {"role": "user", "content": f"TASK:\n{json.dumps(tanim['instructions'], ensure_ascii=False)}\n\n"
                                    f"OPTIONS (choose exactly one key):\n{secenekler}\n\n"
                                    f"INPUT (JSON; backticked names in the task refer to these fields):\n"
                                    f"{json.dumps(state, ensure_ascii=False)}\n\n"
                                    f'Answer format: {{"{alan}": "<one option key>"}}'},
    ]


def coz(metin: str, alan: str, anahtarlar: set[str]) -> str | None:
    """Model çıktısından (düşünme blokları atılarak) son geçerli {alan: anahtar} nesnesi."""
    metin = re.sub(r"<think>.*?</think>", "", metin or "", flags=re.S)
    for m in reversed(re.findall(r"\{[^{}]*\}", metin)):
        try:
            v = json.loads(m).get(alan)
        except (json.JSONDecodeError, AttributeError):
            continue
        if v in anahtarlar:
            return v
    return None


class Yukseltme:
    def __init__(self, motor: Engine, base_url: str, modeller: list[str], api_key: str | None,
                 zaman_asimi: float = 120.0, http: httpx.Client | None = None) -> None:
        self.motor, self.url, self.modeller, self._anahtar = motor, base_url.rstrip("/"), modeller, api_key
        self._c = http or httpx.Client(timeout=zaman_asimi)

    @property
    def hazir(self) -> bool:
        return bool(self._anahtar and self.modeller)

    def sec(self, rol: str, hedef: str, tanim: dict, state: dict, alan: str = "etki") -> tuple[str | None, str | None]:
        """(seçilen anahtar, model) ya da (None, None)."""
        if not self.hazir:
            return None, None
        mesajlar = istem(tanim, state, alan)
        ssha, gsha = kanonik_sha({"tanim": tanim, "alan": alan}), kanonik_sha(state)
        for model in self.modeller:
            t0 = time.perf_counter()
            secim, hata, cikti = None, None, None
            try:
                r = self._c.post(f"{self.url}/chat/completions", headers={"Authorization": f"Bearer {self._anahtar}"},
                                 json={"model": model, "messages": mesajlar, "temperature": 0, "max_tokens": 4096})
                r.raise_for_status()
                cikti = r.json()["choices"][0]["message"].get("content") or ""
                secim = coz(cikti, alan, set(tanim["criteria"]))
                if secim is None:
                    hata = "gecersiz_cikti"
            except Exception as e:  # noqa: BLE001 — sıradaki modele geç
                hata = f"{type(e).__name__}: {e}"[:500]
            with self.motor.begin() as b:
                b.execute(insert(jev_yargi).values(
                    zaman=datetime.now(UTC), rol=rol, saglayici="nvidia", model_istenen=model, model_cozulen=model,
                    soru_sha=ssha, girdi_sha=gsha, hedef=hedef[:256],
                    cevap={alan: {"choice": secim}, "_ham": (cikti or "")[-2000:]} if cikti is not None else None,
                    gecikme_ms=(time.perf_counter() - t0) * 1000, girdi_token=None, hata=hata))
            if secim is not None:
                return secim, model
            _log.warning("yukseltme_basarisiz", model=model, hata=hata)
        return None, None
