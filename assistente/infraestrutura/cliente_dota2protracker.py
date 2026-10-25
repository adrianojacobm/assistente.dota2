# -*- coding: utf-8 -*-
"""Cliente leve para as builds por herói/função do Dota2ProTracker.

O endpoint usado é o mesmo que alimenta as builds do site. Os dados de build
são armazenados por 30 minutos para respeitar o rate limit e reduzir chamadas.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

import requests

from .cache_json import gravar_json, ler_json

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
CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "d2pt"
_trava = threading.Lock()
_ultima_chamada = 0.0
REGISTRO = logging.getLogger(__name__)

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


class ErroDota2ProTracker(RuntimeError):
    """Erro de acesso ou resposta inválida do Dota2ProTracker."""


def obter_json(
    caminho: str, chave_cache: str, validar: Callable[[object], object] | None = None,
) -> object:
    global _ultima_chamada
    arquivo_cache = CACHE_DIR / f"{chave_cache}.json"
    with _trava:
        try:
            idade = time.time() - arquivo_cache.stat().st_mtime
        except OSError:
            idade = CACHE_TTL
        if 0 <= idade < CACHE_TTL:
            cacheado = ler_json(arquivo_cache)
            if cacheado is not None:
                try:
                    if validar is not None:
                        validar(cacheado)
                except ErroDota2ProTracker:
                    REGISTRO.debug("Cache D2PT inválido: %s", arquivo_cache)
                else:
                    return cacheado
        espera = 1.0 - (time.monotonic() - _ultima_chamada)
        if espera > 0:
            time.sleep(espera)
        try:
            resposta = requests.get(f"{BASE}{caminho}", headers=HEADERS, timeout=20)
        except requests.RequestException as erro:
            raise ErroDota2ProTracker(f"Falha de conexão com o Dota2ProTracker: {erro}") from erro
        finally:
            _ultima_chamada = time.monotonic()
        try:
            if resposta.status_code == 403:
                raise ErroDota2ProTracker(
                    "O Dota2ProTracker bloqueou a consulta (HTTP 403/Cloudflare). "
                    "Abra o site no navegador e tente novamente; dados vencidos não foram usados."
                )
            if resposta.status_code != 200:
                raise ErroDota2ProTracker(f"Dota2ProTracker respondeu HTTP {resposta.status_code}.")
            try:
                dados = resposta.json()
            except ValueError as erro:
                raise ErroDota2ProTracker("O Dota2ProTracker não retornou JSON válido.") from erro
        finally:
            resposta.close()
        if validar is not None:
            validar(dados)
        gravar_json(arquivo_cache, dados)
        return dados


def _extrair_builds(payload: object) -> list[dict[str, object]]:
    campos_build = {
        "build_data", "num_matches", "anchor_items", "starting_items_new", "starting_items_combos",
    }
    if isinstance(payload, dict):
        if isinstance(payload.get("builds"), list):
            payload = payload["builds"]
        elif isinstance(payload.get("data"), list):
            payload = payload["data"]
        elif campos_build.intersection(payload):
            payload = [payload]
        else:
            raise ErroDota2ProTracker("Objeto de builds sem campos reconhecidos.")
    if not isinstance(payload, list):
        raise ErroDota2ProTracker("Formato de builds inesperado recebido do Dota2ProTracker.")
    builds = [
        registro for registro in payload if isinstance(registro, dict) and campos_build.intersection(registro)
    ]
    if payload and not builds:
        raise ErroDota2ProTracker("Lista de builds sem campos reconhecidos.")
    return builds


def obter_builds(hero_id: int, role: str) -> list[dict[str, object]]:
    """Busca a lista de builds D2PT para um herói e a posição exata (1–5)."""
    role = (role or "CARRY").upper()
    posicao = ROLE_TO_POSITION.get(role)
    if not posicao:
        raise ErroDota2ProTracker(f"Função não reconhecida: {role}")
    caminho = f"/api/hero/{int(hero_id)}/builds?position={quote(posicao)}"
    dados = obter_json(caminho, f"builds_{int(hero_id)}_{posicao.replace(' ', '')}", _extrair_builds)
    return _extrair_builds(dados)
