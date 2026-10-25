# -*- coding: utf-8 -*-
"""Camada HTTP da OpenDota: cache, rate-limit e normalização de respostas."""
import threading
import time
import json
import os
import re
from typing import Any

import requests

import config

_lock = threading.Lock()
_ultima_chamada = 0.0
_cache = {}  # chave -> (timestamp, dados)
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_opendota")


def _arquivo_cache(cache_key):
    if not cache_key:
        return None
    seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(cache_key))[:180]
    return os.path.join(_CACHE_DIR, seguro + ".json")


def _ler_cache_disco(cache_key, ttl):
    caminho = _arquivo_cache(cache_key)
    if not caminho or ttl <= 0:
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            registro = json.load(arquivo)
        carimbo = float(registro.get("timestamp", 0))
        if time.time() - carimbo < ttl and "data" in registro:
            return carimbo, registro["data"]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


def _gravar_cache_disco(cache_key, timestamp, dados):
    caminho = _arquivo_cache(cache_key)
    if not caminho:
        return
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        temporario = caminho + ".tmp"
        with open(temporario, "w", encoding="utf-8") as arquivo:
            json.dump({"timestamp": timestamp, "data": dados}, arquivo, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporario, caminho)
    except (OSError, TypeError, ValueError):
        # O cache persistente é apenas uma otimização; falhas de disco não
        # podem impedir a consulta nem interromper a interface.
        pass


def _respeitar_rate_limit():
    global _ultima_chamada
    with _lock:
        agora = time.time()
        espera = config.INTERVALO_MIN_ENTRE_CHAMADAS_S - (agora - _ultima_chamada)
        if espera > 0:
            time.sleep(espera)
        _ultima_chamada = time.time()


def _get(path: str, params: dict = None, cache_key: str = None, ttl: float = 0):
    """GET genérico. Retorna None em falha e nunca deixa a UI cair por rede."""
    if cache_key and ttl > 0:
        cacheado = _cache.get(cache_key)
        if cacheado and (time.time() - cacheado[0]) < ttl:
            return cacheado[1]
        cache_disco = _ler_cache_disco(cache_key, ttl)
        if cache_disco:
            _cache[cache_key] = cache_disco
            return cache_disco[1]

    _respeitar_rate_limit()
    try:
        r = requests.get(
            f"{config.OPENDOTA_BASE}{path}",
            params=params,
            headers=config.HEADERS_API,
            timeout=config.TIMEOUT_REQUEST_S,
        )
        if r.status_code != 200:
            print(f"[OpenDota] {path} -> HTTP {r.status_code}")
            return None
        dados = r.json()
    except requests.exceptions.RequestException as e:
        print(f"[OpenDota] Falha de rede em {path}: {e}")
        return None
    except (ValueError, TypeError) as e:
        print(f"[OpenDota] Resposta inválida em {path}: {e}")
        return None

    if cache_key and ttl > 0:
        timestamp = time.time()
        _cache[cache_key] = (timestamp, dados)
        _gravar_cache_disco(cache_key, timestamp, dados)
    return dados


def obter_catalogo_itens():
    """Retorna {item_id: nome}, ignorando recipes."""
    dados = _get("/constants/items", cache_key="constants_items", ttl=config.CACHE_TTL_CATALOGO_S)
    if not isinstance(dados, dict):
        return {}
    catalogo = {}
    for chave, val in dados.items():
        if isinstance(val, dict) and "id" in val and "dname" in val and not chave.startswith("recipe_"):
            try:
                catalogo[int(val["id"])] = val["dname"]
            except (TypeError, ValueError):
                continue
    return catalogo


def obter_catalogo_heroes():
    """Retorna os papéis/atributos oficiais da base dotaconstants."""
    dados = _get("/constants/heroes", cache_key="constants_heroes", ttl=config.CACHE_TTL_CATALOGO_S)
    if not isinstance(dados, dict):
        return {}
    catalogo = {}
    for val in dados.values():
        if isinstance(val, dict) and "id" in val:
            try:
                catalogo[int(val["id"])] = {
                    "roles": val.get("roles", []),
                    "primary_attr": val.get("primary_attr", ""),
                    "attack_type": val.get("attack_type", ""),
                }
            except (TypeError, ValueError):
                continue
    return catalogo


def obter_hero_stats():
    """Lista do /heroStats (picks/wins agregados por herói)."""
    return _get("/heroStats", cache_key="hero_stats", ttl=config.CACHE_TTL_CATALOGO_S)


def obter_item_popularity(hero_id: int):
    """Compras por fase agregadas por herói; o endpoint não filtra função nem matchup."""
    return _get(
        f"/heroes/{hero_id}/itemPopularity",
        cache_key=f"item_pop_{hero_id}",
        ttl=config.CACHE_TTL_ITEM_POPULARITY_S,
    )


def obter_matchups(hero_id: int):
    """Resultados agregados desse herói contra cada adversário."""
    return _get(
        f"/heroes/{hero_id}/matchups",
        cache_key=f"matchups_{hero_id}",
        ttl=config.CACHE_TTL_MATCHUPS_S,
    )


def _valor_percentil(valores: Any, percentil_alvo: float):
    """Interpola um ponto de uma curva de percentis [{percentile, value}, ...]."""
    if not isinstance(valores, list):
        return None
    pontos = []
    for p in valores:
        if not isinstance(p, dict):
            continue
        try:
            pontos.append((float(p["percentile"]), float(p["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not pontos:
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


def obter_benchmarks(hero_id: int, modo: str = "CARRY", percentil: float = None):
    """Retorna benchmarks já normalizados para os campos usados pelo overlay.

    A API devolve um objeto `result` contendo curvas de percentil, não os campos
    `lh_min`/`gpm` esperados pelo overlay. CARRY/MID usam a curva core e SUP usa
    support; o ponto padrão é o percentil 50.
    """
    if percentil is None:
        percentil = config.PERCENTIL_BENCHMARK
    role_api = "support" if str(modo).upper() in ("SUP", "HARD_SUPPORT") else "core"
    cache_key = f"bench_{hero_id}_{role_api}_{percentil:.3f}"
    bruto = _get(
        "/benchmarks",
        params={"hero_id": hero_id, "role": role_api},
        cache_key=cache_key,
        ttl=config.CACHE_TTL_BENCHMARKS_S,
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
    normalizado = {chave: _valor_percentil(curvas.get(nome_api), percentil)
                   for chave, nome_api in nomes_api.items()}
    normalizado["percentil"] = percentil
    normalizado["role"] = role_api
    normalizado["fonte"] = "OpenDota /benchmarks"
    # Resposta vazia não deve ser tratada como se tivesse benchmarks válidos.
    if all(normalizado[k] is None for k in nomes_api):
        return None
    return normalizado


def obter_partidas_heroi(hero_id: int, limit: int = 100, offset: int = 0):
    """Página de partidas do herói, da mais recente para a mais antiga."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    return _get(
        f"/heroes/{hero_id}/matches",
        params={"limit": limit, "offset": offset},
        cache_key=f"hero_matches_{hero_id}_{limit}_{offset}",
        ttl=config.CACHE_TTL_PARTIDAS_HEROI_S,
    )


def obter_catalogo_precos_itens():
    """Mapa {nome do item: custo em ouro} usando o catálogo OpenDota atual."""
    dados = _get("/constants/items", cache_key="constants_items", ttl=config.CACHE_TTL_CATALOGO_S)
    if not isinstance(dados, dict):
        return {}
    precos = {}
    for chave, val in dados.items():
        if not isinstance(val, dict) or not val.get("dname") or str(chave).startswith("recipe_"):
            continue
        try:
            custo = int(val.get("cost"))
        except (TypeError, ValueError):
            continue
        if custo >= 0:
            precos[str(val["dname"])] = custo
    return precos


def obter_detalhes_partida(match_id: int):
    """Detalhes parseados de uma partida, incluindo jogadores e purchase_log quando disponível."""
    return _get(
        f"/matches/{match_id}",
        cache_key=f"match_detail_{match_id}",
        ttl=config.CACHE_TTL_DETALHE_PARTIDA_S,
    )


def obter_catalogo_chaves_itens():
    """Mapeia a chave interna usada em purchase_log para o nome visível do item."""
    dados = _get("/constants/items", cache_key="constants_items", ttl=config.CACHE_TTL_CATALOGO_S)
    if not isinstance(dados, dict):
        return {}
    return {
        str(chave): val.get("dname")
        for chave, val in dados.items()
        if isinstance(val, dict) and val.get("dname") and not str(chave).startswith("recipe_")
    }


def obter_catalogo_receitas_itens():
    """Retorna {nome_item: [componentes]} usando o catálogo oficial.

    A receita (recipe_<item>) é preservada como token virtual nos upgrades pagos
    de um único componente. Isso impede falsos upgrades gratuitos como Gloves of
    Haste -> Hand of Midas ou Boots of Travel -> Boots of Travel 2. Itens com dois
    ou mais componentes continuam sendo reconstruídos quando estes aparecem no log,
    inclusive em casos em que o replay omite a receita do purchase_log.
    """
    dados = _get("/constants/items", cache_key="constants_items", ttl=config.CACHE_TTL_CATALOGO_S)
    if not isinstance(dados, dict):
        return {}

    nome_por_chave = {
        str(chave): val.get("dname")
        for chave, val in dados.items()
        if isinstance(val, dict) and val.get("dname")
    }
    receitas = {}
    for chave, val in dados.items():
        if not isinstance(val, dict) or str(chave).startswith("recipe_"):
            continue
        nome = val.get("dname")
        componentes = val.get("components")
        if not nome or not isinstance(componentes, list) or not componentes:
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
        except (TypeError, ValueError):
            recipe_cost = 0
        if recipe_cost > 0 and len(nomes_componentes) <= 1:
            nomes_componentes.append(f"__RECIPE__:{nome}")
        receitas[str(nome)] = nomes_componentes
    return receitas
