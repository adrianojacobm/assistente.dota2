# -*- coding: utf-8 -*-
"""Cliente leve para as builds por herói/função do Dota2ProTracker.

O endpoint usado é o mesmo que alimenta as builds do site. Os dados de build
são armazenados por 30 minutos para respeitar o rate limit e reduzir chamadas.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

BASE = "https://dota2protracker.com"
CACHE_TTL = 30 * 60
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://dota2protracker.com/",
    "Accept": "application/json, text/plain, */*",
}
CACHE_DIR = Path(__file__).resolve().parent / "cache" / "d2pt"
_lock = threading.Lock()
_last_request = 0.0

ROLE_TO_POSITION = {
    "CARRY": "pos 1",
    "MID": "pos 2",
    "OFFLANE": "pos 3",
    "SUP": "pos 4",
    "HARD_SUPPORT": "pos 5",
}
ROLE_LABELS = {
    "CARRY": "Carry",
    "MID": "Mid",
    "OFFLANE": "Offlane",
    "SUP": "Support",
    "HARD_SUPPORT": "Hard Support",
}


class D2PTError(RuntimeError):
    """Erro de acesso ou resposta inválida do Dota2ProTracker."""


def _get_json(path: str, cache_key: str):
    global _last_request
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < CACHE_TTL:
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    url = f"{BASE}{path}"
    with _lock:
        wait = 1.0 - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            _last_request = time.monotonic()
        except requests.RequestException as exc:
            raise D2PTError(f"Falha de conexão com o Dota2ProTracker: {exc}") from exc

    if response.status_code == 403:
        raise D2PTError(
            "O Dota2ProTracker bloqueou a consulta (HTTP 403/Cloudflare). "
            "Abra o site normalmente no navegador e tente novamente; nenhum dado antigo foi apresentado como atual."
        )
    if response.status_code != 200:
        raise D2PTError(f"Dota2ProTracker respondeu HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise D2PTError("O Dota2ProTracker não retornou JSON válido (possível desafio do Cloudflare).") from exc
    try:
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return payload


def obter_builds(hero_id: int, role: str) -> list[dict]:
    """Busca a lista de builds D2PT para um herói e a posição exata (1–5)."""
    role = (role or "CARRY").upper()
    position = ROLE_TO_POSITION.get(role)
    if not position:
        raise D2PTError(f"Função não reconhecida: {role}")
    path = f"/api/hero/{int(hero_id)}/builds?position={quote(position)}"
    payload = _get_json(path, f"builds_{int(hero_id)}_{position.replace(' ', '')}")
    if isinstance(payload, dict):
        if isinstance(payload.get("builds"), list):
            payload = payload["builds"]
        elif isinstance(payload.get("data"), list):
            payload = payload["data"]
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise D2PTError("Formato de builds inesperado recebido do Dota2ProTracker.")
    return [b for b in payload if isinstance(b, dict)]
