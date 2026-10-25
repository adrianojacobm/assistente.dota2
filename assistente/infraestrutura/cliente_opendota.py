# -*- coding: utf-8 -*-
"""Camada HTTP da OpenDota: cache, rate-limit e normalização de respostas."""
import logging
import math
import os
import re
import threading
import time
from pathlib import Path

import requests

from assistente import configuracao

from .cache_json import gravar_json, ler_json

_lock = threading.Lock()
_ultima_chamada = 0.0
_cache: dict[str, tuple[float, object]] = {}
_CACHE_DIR = str(Path(__file__).resolve().parents[2] / "cache_opendota")
REGISTRO = logging.getLogger(__name__)


def _arquivo_cache(cache_key: str | None) -> str | None:
    if not cache_key:
        return None
    seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(cache_key))[:180]
    return os.path.join(_CACHE_DIR, seguro + ".json")


def _ler_cache_disco(cache_key: str, ttl: float) -> tuple[float, object] | None:
    caminho = _arquivo_cache(cache_key)
    if not caminho or ttl <= 0:
        return None
    try:
        registro = ler_json(Path(caminho))
        if not isinstance(registro, dict):
            return None
        carimbo = float(registro.get("timestamp", 0))
        if math.isfinite(carimbo) and 0 <= time.time() - carimbo < ttl and "data" in registro:
            return carimbo, registro["data"]
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def _gravar_cache_disco(cache_key: str, timestamp: float, dados: object) -> None:
    caminho = _arquivo_cache(cache_key)
    if not caminho:
        return
    gravar_json(Path(caminho), {"timestamp": timestamp, "data": dados})


def _respeitar_rate_limit() -> None:
    global _ultima_chamada
    agora = time.monotonic()
    espera = configuracao.INTERVALO_MIN_ENTRE_CHAMADAS_S - (agora - _ultima_chamada)
    if espera > 0:
        time.sleep(espera)
    _ultima_chamada = time.monotonic()


def _get(
    path: str, params: dict[str, int | str] | None = None,
    cache_key: str | None = None, ttl: float = 0, tipo_esperado: type[object] | None = None,
) -> object:
    # A API é limitada a aproximadamente uma chamada por segundo: uma trava
    # simples também impede consultas simultâneas da mesma chave antes do cache.
    with _lock:
        return _consultar(path, params, cache_key, ttl, tipo_esperado)


def _consultar(
    path: str, params: dict[str, int | str] | None, cache_key: str | None, ttl: float,
    tipo_esperado: type[object] | None,
) -> object:
    """GET genérico. Retorna None em falha e nunca deixa a UI cair por rede."""
    if cache_key and ttl > 0:
        cacheado = _cache.get(cache_key)
        if (cacheado and 0 <= (time.time() - cacheado[0]) < ttl
                and (tipo_esperado is None or isinstance(cacheado[1], tipo_esperado))):
            return cacheado[1]
        cache_disco = _ler_cache_disco(cache_key, ttl)
        if cache_disco and (tipo_esperado is None or isinstance(cache_disco[1], tipo_esperado)):
            _cache[cache_key] = cache_disco
            return cache_disco[1]

    _respeitar_rate_limit()
    try:
        resposta = requests.get(
            f"{configuracao.OPENDOTA_BASE}{path}",
            params=params,
            headers=configuracao.HEADERS_API,
            timeout=configuracao.TIMEOUT_REQUEST_S,
        )
        try:
            if resposta.status_code != 200:
                REGISTRO.warning("OpenDota %s: HTTP %s", path, resposta.status_code)
                return None
            dados = resposta.json()
        finally:
            resposta.close()
    except requests.exceptions.RequestException as e:
        REGISTRO.warning("Falha de rede OpenDota %s: %s", path, e)
        return None
    except (ValueError, TypeError) as e:
        REGISTRO.warning("Resposta OpenDota inválida em %s: %s", path, e)
        return None

    if tipo_esperado is not None and not isinstance(dados, tipo_esperado):
        REGISTRO.warning("Formato inesperado retornado pela OpenDota em %s.", path)
        return None
    if cache_key and ttl > 0:
        timestamp = time.time()
        _cache[cache_key] = (timestamp, dados)
        _gravar_cache_disco(cache_key, timestamp, dados)
    return dados


def obter_catalogo_itens() -> dict[int, str]:
    """Retorna {item_id: nome}, ignorando recipes."""
    dados = _get(
        "/constants/items", cache_key="constants_items", ttl=configuracao.CACHE_TTL_CATALOGO_S,
        tipo_esperado=dict,
    )
    if not isinstance(dados, dict):
        return {}
    catalogo: dict[int, str] = {}
    for chave, val in dados.items():
        if (isinstance(val, dict) and "id" in val and isinstance(val.get("dname"), str)
                and not str(chave).startswith("recipe_")):
            try:
                catalogo[int(val["id"])] = val["dname"]
            except (TypeError, ValueError, OverflowError):
                continue
    return catalogo


def obter_catalogo_heroes() -> dict[int, dict[str, object]]:
    """Retorna os papéis/atributos oficiais da base dotaconstants."""
    dados = _get(
        "/constants/heroes", cache_key="constants_heroes", ttl=configuracao.CACHE_TTL_CATALOGO_S,
        tipo_esperado=dict,
    )
    if not isinstance(dados, dict):
        return {}
    catalogo: dict[int, dict[str, object]] = {}
    for val in dados.values():
        if isinstance(val, dict) and "id" in val:
            try:
                catalogo[int(val["id"])] = {
                    "roles": val.get("roles", []),
                    "primary_attr": val.get("primary_attr", ""),
                    "attack_type": val.get("attack_type", ""),
                }
            except (TypeError, ValueError, OverflowError):
                continue
    return catalogo


def obter_hero_stats() -> object:
    """Lista do /heroStats (picks/wins agregados por herói)."""
    return _get(
        "/heroStats", cache_key="hero_stats", ttl=configuracao.CACHE_TTL_CATALOGO_S,
        tipo_esperado=list,
    )


def obter_item_popularity(hero_id: int) -> object:
    """Compras por fase agregadas por herói; o endpoint não filtra função nem matchup."""
    return _get(
        f"/heroes/{hero_id}/itemPopularity",
        cache_key=f"item_pop_{hero_id}",
        ttl=configuracao.CACHE_TTL_ITEM_POPULARITY_S,
        tipo_esperado=dict,
    )


def obter_matchups(hero_id: int) -> object:
    """Resultados agregados desse herói contra cada adversário."""
    return _get(
        f"/heroes/{hero_id}/matchups",
        cache_key=f"matchups_{hero_id}",
        ttl=configuracao.CACHE_TTL_MATCHUPS_S,
        tipo_esperado=list,
    )


def _valor_percentil(valores: object, percentil_alvo: float) -> float | None:
    """Interpola um ponto de uma curva de percentis [{percentile, value}, ...]."""
    if not isinstance(valores, list):
        return None
    pontos = []
    for p in valores:
        if not isinstance(p, dict):
            continue
        if isinstance(p.get("percentile"), bool) or isinstance(p.get("value"), bool):
            continue
        try:
            percentil, valor = float(p["percentile"]), float(p["value"])
            if math.isfinite(percentil) and math.isfinite(valor) and 0 <= percentil <= 1 and valor >= 0:
                pontos.append((percentil, valor))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if not pontos or not math.isfinite(percentil_alvo):
        return None
    pontos.sort(key=lambda x: x[0])
    alvo = min(max(float(percentil_alvo), pontos[0][0]), pontos[-1][0])
    for p, valor in pontos:
        if p == alvo:
            return valor
    for (p0, v0), (p1, v1) in zip(pontos, pontos[1:]):
        if p0 <= alvo <= p1:
            if p1 == p0:
                return v0
            proporcao = (alvo - p0) / (p1 - p0)
            return v0 + (v1 - v0) * proporcao
    return pontos[-1][1]


def obter_benchmarks(
    hero_id: int, modo: str = "CARRY", percentil: float | None = None,
) -> dict[str, object] | None:
    """Retorna benchmarks já normalizados para os campos usados pelo overlay.

    A API devolve um objeto `result` contendo curvas de percentil, não os campos
    `lh_min`/`gpm` esperados pelo overlay. Preserva o parâmetro core/support;
    sua efetividade depende do contrato do provedor. O padrão é o percentil 50.
    """
    if percentil is None:
        percentil = configuracao.PERCENTIL_BENCHMARK
    if not math.isfinite(percentil) or not 0 <= percentil <= 1:
        raise ValueError("O percentil precisa estar entre zero e um.")
    role_api = "support" if str(modo).upper() in ("SUP", "HARD_SUPPORT") else "core"
    cache_key = f"bench_{hero_id}_{role_api}_{percentil:.3f}"
    bruto = _get(
        "/benchmarks",
        params={"hero_id": hero_id, "role": role_api},
        cache_key=cache_key,
        ttl=configuracao.CACHE_TTL_BENCHMARKS_S,
        tipo_esperado=dict,
    )
    if not isinstance(bruto, dict):
        return None
    curvas = bruto.get("result", {})
    if not isinstance(curvas, dict):
        return None

    nomes_api = {
        "gpm": "gold_per_min",
        "xpm": "xp_per_min",
        "lh_min": "last_hits_per_min",
        "dn_min": "denies_per_min",
        "k_min": "kills_per_min",
        "a_min": "assists_per_min",
        "dpm": "hero_damage_per_min",
        "heal_min": "hero_healing_per_min",
    }
    normalizado: dict[str, object] = {
        chave: _valor_percentil(curvas.get(nome_api), percentil)
        for chave, nome_api in nomes_api.items()
    }
    normalizado["percentil"] = percentil
    normalizado["role"] = role_api
    normalizado["fonte"] = "OpenDota /benchmarks"
    # Resposta vazia não deve ser tratada como se tivesse benchmarks válidos.
    if all(normalizado[k] is None for k in nomes_api):
        return None
    return normalizado


def obter_partidas_heroi(hero_id: int, limit: int = 100, offset: int = 0) -> object:
    """Página de partidas do herói, da mais recente para a mais antiga."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    return _get(
        f"/heroes/{hero_id}/matches",
        params={"limit": limit, "offset": offset},
        cache_key=f"hero_matches_{hero_id}_{limit}_{offset}",
        ttl=configuracao.CACHE_TTL_PARTIDAS_HEROI_S,
        tipo_esperado=list,
    )


def obter_catalogo_precos_itens() -> dict[str, int]:
    """Mapa {nome do item: custo em ouro} usando o catálogo OpenDota atual."""
    dados = _get(
        "/constants/items", cache_key="constants_items", ttl=configuracao.CACHE_TTL_CATALOGO_S,
        tipo_esperado=dict,
    )
    if not isinstance(dados, dict):
        return {}
    precos = {}
    for chave, val in dados.items():
        if (not isinstance(val, dict) or not isinstance(val.get("dname"), str)
                or not val["dname"] or str(chave).startswith("recipe_")):
            continue
        try:
            custo = int(val.get("cost"))
        except (TypeError, ValueError, OverflowError):
            continue
        if custo >= 0:
            precos[str(val["dname"])] = custo
    return precos


def obter_detalhes_partida(match_id: int) -> object:
    """Detalhes parseados de uma partida, incluindo jogadores e purchase_log quando disponível."""
    return _get(
        f"/matches/{match_id}",
        cache_key=f"match_detail_{match_id}",
        ttl=configuracao.CACHE_TTL_DETALHE_PARTIDA_S,
        tipo_esperado=dict,
    )


def obter_catalogo_chaves_itens() -> dict[str, str]:
    """Mapeia a chave interna usada em purchase_log para o nome visível do item."""
    dados = _get(
        "/constants/items", cache_key="constants_items", ttl=configuracao.CACHE_TTL_CATALOGO_S,
        tipo_esperado=dict,
    )
    if not isinstance(dados, dict):
        return {}
    return {
        str(chave): val.get("dname")
        for chave, val in dados.items()
        if isinstance(val, dict) and isinstance(val.get("dname"), str)
        and val["dname"] and not str(chave).startswith("recipe_")
    }


def obter_catalogo_receitas_itens() -> dict[str, list[str]]:
    """Retorna {nome_item: [componentes]} usando o catálogo oficial.

    A receita (recipe_<item>) é preservada como token virtual nos upgrades pagos
    de um único componente. Isso impede falsos upgrades gratuitos como Gloves of
    Haste -> Hand of Midas ou Boots of Travel -> Boots of Travel 2. Itens com dois
    ou mais componentes continuam sendo reconstruídos quando estes aparecem no log,
    inclusive em casos em que o replay omite a receita do purchase_log.
    """
    dados = _get(
        "/constants/items", cache_key="constants_items", ttl=configuracao.CACHE_TTL_CATALOGO_S,
        tipo_esperado=dict,
    )
    if not isinstance(dados, dict):
        return {}

    nome_por_chave = {
        str(chave): val.get("dname")
        for chave, val in dados.items()
        if isinstance(val, dict) and isinstance(val.get("dname"), str) and val["dname"]
    }
    receitas = {}
    for chave, val in dados.items():
        if not isinstance(val, dict) or str(chave).startswith("recipe_"):
            continue
        nome = val.get("dname")
        componentes = val.get("components")
        if not isinstance(nome, str) or not nome or not isinstance(componentes, list) or not componentes:
            continue
        nomes_componentes = []
        for comp in componentes:
            comp = str(comp)
            if comp.startswith("recipe_"):
                continue
            comp_nome = nome_por_chave.get(comp)
            if not comp_nome and comp.startswith("item_"):
                comp_nome = nome_por_chave.get(comp[len("item_"):])
            if not comp_nome:
                nomes_componentes = []
                break
            nomes_componentes.append(comp_nome)
        if not nomes_componentes:
            continue

        receita_key = f"recipe_{chave}"
        recipe_val = dados.get(receita_key)
        try:
            recipe_cost = int((recipe_val or {}).get("cost", 0)) if isinstance(recipe_val, dict) else 0
        except (TypeError, ValueError, OverflowError):
            recipe_cost = 0
        if recipe_cost > 0 and len(nomes_componentes) <= 1:
            nomes_componentes.append(f"__RECIPE__:{nome}")
        receitas[str(nome)] = nomes_componentes
    return receitas
