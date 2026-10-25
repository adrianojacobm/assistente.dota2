# -*- coding: utf-8 -*-
"""Build por fases, com ranking sensível à função escolhida.

Limitação da fonte: OpenDota /itemPopularity agrega compras por herói e fase; não
permite filtrar por função nem por herói adversário. Por isso, o script não finge
que contagens agregadas sejam builds específicas de uma matchup. A função altera
prioridade/filtros de itens observados; alertas de lane são heurísticos e rotulados.
"""
import threading

import config
import opendota_client as api
from hero_data import HERO_IDS, COMPONENTES_SOLTOS

_catalogo_itens = {}
_catalogo_heroes = {}
_carregando = False
_lock_catalogo = threading.Lock()
_evento_catalogo = threading.Event()

# Ordenação de desempate/ênfase por função. Só reordena itens que a API observou
# para o próprio herói: não injeta um item que não veio dos dados.
PREFERENCIAS_FUNCAO = {
    "CARRY": [
        "Power Treads", "Phase Boots", "Magic Wand", "Dragon Lance", "Hurricane Pike",
        "Manta Style", "Black King Bar", "Daedalus", "Butterfly", "Satanic",
        "Monkey King Bar", "Abyssal Blade", "Sange and Yasha", "Swift Blink",
        "Mjollnir", "Maelstrom", "Desolator", "Silver Edge", "Eye of Skadi",
        "Aghanim's Scepter", "Aghanim's Shard", "Boots of Travel",
    ],
    "MID": [
        "Bottle", "Power Treads", "Phase Boots", "Magic Wand", "Witch Blade",
        "Eul's Scepter of Divinity", "Kaya and Sange", "Black King Bar", "Blink Dagger",
        "Aghanim's Scepter", "Aghanim's Shard", "Shiva's Guard", "Scythe of Vyse",
        "Orchid Malevolence", "Bloodthorn", "Refresher Orb", "Boots of Travel",
        "Linken's Sphere", "Hurricane Pike", "Daedalus",
    ],
    "SUP": [
        "Arcane Boots", "Tranquil Boots", "Magic Wand", "Aether Lens", "Force Staff",
        "Glimmer Cape", "Solar Crest", "Mekansm", "Guardian Greaves", "Holy Locket",
        "Pavise", "Lotus Orb", "Eul's Scepter of Divinity", "Blink Dagger",
        "Aghanim's Shard", "Aghanim's Scepter", "Ghost Scepter", "Aeon Disk",
        "Gleipnir", "Scythe of Vyse",
    ],
}

# Cortes conservadores para não importar o núcleo de um carry para uma build de
# suporte ou itens utilitários de suporte para os primeiros slots de carry.
EXCLUIR_POR_FUNCAO = {
    "SUP": {"Battle Fury", "Daedalus", "Divine Rapier", "Butterfly", "Satanic", "Radiance", "Mjollnir"},
    "CARRY": {"Mekansm", "Guardian Greaves", "Glimmer Cape", "Solar Crest", "Pipe of Insight", "Crimson Guard", "Holy Locket", "Pavise"},
    "MID": set(),
}

RECEITAS = {"Recipe"}
PERGAMINHOS_TELEPORTE = {
    "town portal scroll", "teleport scroll", "teleportation scroll", "tp scroll",
}


def garantir_catalogo(aguardar=True):
    """Carrega catálogos uma vez; o worker de API pode esperar sem bloquear Tkinter."""
    global _catalogo_itens, _catalogo_heroes, _carregando
    with _lock_catalogo:
        if _catalogo_itens and _catalogo_heroes:
            return
        if not _carregando:
            _carregando = True
            _evento_catalogo.clear()

            def _worker():
                global _catalogo_itens, _catalogo_heroes, _carregando
                try:
                    itens = api.obter_catalogo_itens() or {}
                    heroes = api.obter_catalogo_heroes() or {}
                    with _lock_catalogo:
                        _catalogo_itens = itens
                        _catalogo_heroes = heroes
                finally:
                    with _lock_catalogo:
                        _carregando = False
                    _evento_catalogo.set()

            threading.Thread(target=_worker, daemon=True).start()
    if aguardar:
        _evento_catalogo.wait(timeout=config.TIMEOUT_REQUEST_S * 2 + 3)
    return


def _rankear_por_funcao(itens, modo, fase):
    modo = modo if modo in PREFERENCIAS_FUNCAO else "CARRY"
    excluir = EXCLUIR_POR_FUNCAO[modo]
    itens = [it for it in itens if it["nome"] not in excluir]
    # A saída inicial segue a frequência observada: preferências de itens de core
    # não podem empurrar Tango/Branches para fora da lista de start.
    if fase == "start":
        return sorted(itens, key=lambda it: -it["contagem"])
    preferidos = {nome: i for i, nome in enumerate(PREFERENCIAS_FUNCAO[modo])}
    # Mantém apenas itens vistos nos dados e favorece o perfil de função; frequência
    # é o desempate. Não é uma estatística por função (a API não oferece esse filtro).
    return sorted(itens, key=lambda it: (preferidos.get(it["nome"], 10_000), -it["contagem"]))


def _classificar_itens(dict_stage: dict, limite: int, fase: str, modo: str):
    """Lista nomes mais comprados; nunca exibe percentuais calculados incorretamente."""
    if not isinstance(dict_stage, dict) or not _catalogo_itens:
        return []
    resultado = []
    vistos = set()
    for item_id_str, count in sorted(dict_stage.items(), key=lambda kv: _int_seguro(kv[1]), reverse=True):
        try:
            item_id = int(item_id_str)
            quantidade = _int_seguro(count)
        except (TypeError, ValueError):
            continue
        nome = _catalogo_itens.get(item_id)
        if not nome or nome in RECEITAS or nome in vistos:
            continue
        if nome.strip().lower() in PERGAMINHOS_TELEPORTE:
            continue
        # Na saída inicial, Tango/Salve/Clarity/Branches e outros componentes são
        # compras reais de saída. Nas demais fases removemos componentes de receita.
        if fase != "start" and nome in COMPONENTES_SOLTOS:
            continue
        resultado.append({"nome": nome, "contagem": quantidade})
        vistos.add(nome)
    resultado = _rankear_por_funcao(resultado, modo, fase)
    return resultado[:max(1, limite)]


def _int_seguro(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _formatar_fase(itens):
    return " → ".join(it["nome"] for it in itens) if itens else "Sem amostra suficiente para esta fase."


def obter_build_contextualizada(meu_heroi: str, modo: str, lane1: str, lane2: str, ameaca: str,
                                usar_agregado: bool = False) -> dict:
    """Build por função vinda do Dota2ProTracker, com fallback explícito em erros.

    A fonte organiza a saída inicial, progressão e itens situacionais por posição.
    Counters contra Lane 1/Lane 2/Ameaça são adicionados separadamente pelo app.
    """
    import d2pt_client

    role = (modo or "CARRY").upper()
    if role not in d2pt_client.ROLE_TO_POSITION:
        role = "CARRY"
    hid = HERO_IDS.get(meu_heroi)
    if not hid:
        return _resultado_vazio(meu_heroi, role, "Herói não encontrado.")

    try:
        builds = d2pt_client.obter_builds(hid, role)
    except Exception as exc:
        return _resultado_vazio(
            meu_heroi, role,
            f"Não foi possível consultar o Dota2ProTracker: {exc}. A build não foi substituída por dados de outra fonte."
        )

    if not builds:
        return _resultado_vazio(
            meu_heroi, role,
            f"O Dota2ProTracker não retornou build para {meu_heroi} na função {d2pt_client.ROLE_LABELS[role]} ({d2pt_client.ROLE_TO_POSITION[role]})."
        )

    # O endpoint pode devolver mais de um facet/arquetipo de build para a posição.
    # Pegamos a build com a maior amostra, evitando que uma partida particular domine.
    def _n_partidas(b):
        try:
            return int(b.get("num_matches") or 0)
        except (TypeError, ValueError):
            return 0

    builds.sort(key=_n_partidas, reverse=True)
    build = builds[0]
    bd = build.get("build_data") if isinstance(build.get("build_data"), dict) else build
    try:
        catalogo = api.obter_catalogo_itens() or {}
        precos = api.obter_catalogo_precos_itens() or {}
    except Exception as exc:
        return _resultado_vazio(meu_heroi, role, f"Build D2PT recebida, mas o catálogo de itens/preços não carregou: {exc}")
    if not catalogo:
        return _resultado_vazio(meu_heroi, role, "Build D2PT recebida, mas não foi possível mapear os IDs dos itens.")

    def _item_nome(raw_id):
        try:
            return catalogo.get(int(raw_id))
        except (TypeError, ValueError):
            if isinstance(raw_id, str):
                # Alguns payloads antigos usam nomes internos item_...
                raw = raw_id.removeprefix("item_")
                return raw.replace("_", " ").title()
            return None

    proibidos = {"observer ward", "sentry ward", "observer and sentry wards", "town portal scroll",
                 "teleport scroll", "teleportation scroll", "tp scroll", "recipe"}
    def _filtrar_itens_inicio(ids):
        nomes = []
        for item_id in ids:
            nome = _item_nome(item_id)
            if not nome or nome.strip().lower() in proibidos:
                continue
            nomes.append(nome)
        return nomes

    def _start_ids(entry):
        # Formato D2PT atual: [ [item_id, ...], stats ]; tolera formatos mais antigos.
        if isinstance(entry, (list, tuple)) and entry:
            first = entry[0]
            if isinstance(first, (list, tuple)):
                return list(first)
            if all(isinstance(x, (int, str)) for x in entry):
                return list(entry)
        if isinstance(entry, dict):
            items = entry.get("items") or entry.get("item_ids") or entry.get("raw_item_ids")
            if isinstance(items, list):
                return items
        return []

    pacotes = bd.get("starting_items_new") or bd.get("starting_items_combos") or []
    pacote_selecionado = []
    custo_selecionado = None
    for entry in pacotes if isinstance(pacotes, list) else []:
        nomes = _filtrar_itens_inicio(_start_ids(entry))
        if not nomes:
            continue
        custo = 0
        custo_valido = True
        for nome in nomes:
            if nome not in precos:
                custo_valido = False
                break
            custo += int(precos[nome])
        if custo_valido and custo <= config.ORCAMENTO_SAIDA_INICIAL:
            pacote_selecionado, custo_selecionado = nomes, custo
            break  # os pacotes vêm ordenados por frequência no próprio site

    def _compactar_quantidades(nomes):
        contagem = {}
        ordem = []
        for nome in nomes:
            if nome not in contagem:
                contagem[nome] = 0
                ordem.append(nome)
            contagem[nome] += 1
        return [f"{n} ×{contagem[n]}" if contagem[n] > 1 else n for n in ordem]

    start_items = _compactar_quantidades(pacote_selecionado)
    start_text = " → ".join(start_items) if start_items else ""

    # Construir pool único dos itens de progressão e respetivas estatísticas.
    pool_by_id = {}
    for key in ("anchor_items", "anchor_items2", "items_mid_late"):
        entries = bd.get(key) or []
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            raw_id = e.get("raw_item_id", e.get("item_id", e.get("id")))
            try:
                iid = int(raw_id)
            except (TypeError, ValueError):
                continue
            current = pool_by_id.get(iid)
            e_count = _safe_num(e.get("count"), 0)
            c_count = _safe_num((current or {}).get("count"), 0)
            if current is None or e_count > c_count or (e_count == c_count and _pick_rate(e) > _pick_rate(current)):
                pool_by_id[iid] = e

    pool = []
    ocultos = {"oblivion staff", "recipe", "observer ward", "sentry ward", "town portal scroll", "teleport scroll"}
    for iid, e in pool_by_id.items():
        nome = _item_nome(iid)
        if not nome or nome.strip().lower() in ocultos or nome in COMPONENTES_SOLTOS:
            continue
        if nome.strip().lower() in proibidos:
            continue
        avg = e.get("avg_minute")
        if avg is None:
            continue
        try:
            avg = float(avg)
        except (TypeError, ValueError):
            continue
        pr = _pick_rate(e)
        if pr <= 0:
            continue
        try:
            wr = float(e.get("win_rate") or 0)
            if wr > 1:
                wr /= 100
        except (TypeError, ValueError):
            wr = 0
        pool.append({"nome": nome, "minuto": avg, "pr": pr, "wr": wr, "count": _safe_num(e.get("count"), 0)})

    # O D2PT ordena os itens por horário médio de compra; mantemos essa ordem.
    fases = {"early": [], "mid": [], "late": []}
    situacionais = []
    for fase, predicado in (
        ("early", lambda m: m < 12),
        ("mid", lambda m: 12 <= m < 30),
        ("late", lambda m: m >= 30),
    ):
        nessa_fase = [it for it in pool if predicado(it["minuto"])]
        core = sorted((it for it in nessa_fase if it["pr"] >= 0.50), key=lambda it: (it["minuto"], -it["pr"]))
        fases[fase] = list(dict.fromkeys(it["nome"] for it in core))
        situ = sorted((it for it in nessa_fase if 0.05 <= it["pr"] < 0.50), key=lambda it: (-it["pr"], it["minuto"]))
        situacionais.extend({**it, "fase": fase} for it in situ[:8])

    # Quando o dado agrupa apenas a bota completa, mostrar Boots of Speed antes dela
    # caso não esteja explicitamente presente; esta é a etapa de receita necessária.
    botas_final = {"Power Treads", "Phase Boots", "Arcane Boots", "Tranquil Boots", "Boots of Travel", "Boots of Travel 2"}
    todas_fases = fases["early"] + fases["mid"] + fases["late"]
    if any(nome in botas_final for nome in todas_fases) and "Boots of Speed" not in todas_fases:
        fases["early"].insert(0, "Boots of Speed")

    amostra = _n_partidas(build)
    win_rate = build.get("win_rate")
    if win_rate is None:
        wins = _safe_num(build.get("num_wins"), 0)
        win_rate = wins / amostra if amostra else None
    try:
        win_rate = float(win_rate) if win_rate is not None else None
        if win_rate is not None and win_rate > 1:
            win_rate /= 100
    except (TypeError, ValueError):
        win_rate = None

    def _seta(lista):
        return " → ".join(lista) if lista else ""

    situacionais_texto = []
    rotulo_fase = {"early": "Early (<12m)", "mid": "Mid (12–30m)", "late": "Late (30m+)"}
    for it in sorted(situacionais, key=lambda x: (x["fase"], -x["pr"])):
        situacionais_texto.append(f"{it['nome']} — {it['pr']*100:.0f}% · {rotulo_fase[it['fase']]} · média {it['minuto']:.0f}m")

    build_name = build.get("name") or build.get("label") or build.get("archetype") or "build mais frequente"
    info = [
        f"Fonte: Dota2ProTracker · posição {d2pt_client.ROLE_TO_POSITION[role]} · {amostra} partidas na build selecionada.",
        "Fonte do site: partidas recentes de alto MMR/pro players; janela aproximada de 8 dias, conforme a disponibilidade do herói e da função.",
        "Core = item comprado em ≥50% da amostra, ordenado pelo tempo médio de compra; itens menos frequentes ficam como situacionais no painel.",
    ]
    if win_rate is not None:
        info.append(f"Win rate da build: {win_rate*100:.1f}%.")
    if pacote_selecionado:
        info.append(f"Saída mais comum dentro do orçamento: {', '.join(start_items)} — {custo_selecionado}/{config.ORCAMENTO_SAIDA_INICIAL} de ouro.")
    elif pacotes:
        info.append(f"Nenhum dos pacotes de saída da fonte coube no orçamento de {config.ORCAMENTO_SAIDA_INICIAL}; Saída ficou vazia em vez de inventar itens.")
    else:
        info.append("O site não forneceu combinações de Saída estruturadas para esta build.")
    if situacionais_texto:
        info.append("Situacionais D2PT (não são counters automáticos):\n" + "\n".join(f"• {x}" for x in situacionais_texto[:18]))

    return {
        "heroi": meu_heroi,
        "perfil": d2pt_client.ROLE_LABELS[role].upper(),
        "start": start_text,
        "early": _seta(fases["early"]),
        "mid": _seta(fases["mid"]),
        "late": _seta(fases["late"]),
        "core": "\n".join([f"EARLY: {_seta(fases['early'])}", f"MID: {_seta(fases['mid'])}", f"LATE: {_seta(fases['late'])}"]),
        "alertas": [],
        "analise_matchup": f"Build D2PT selecionada: {build_name}. Os counters por inimigo são calculados separadamente.",
        "fonte": "Dota2ProTracker JSON API",
        "observacao": "\n".join(info),
        "situacionais": situacionais_texto,
        "opcoes": [],
        "amostra": amostra,
        "custo_saida": custo_selecionado,
    }


def _safe_num(valor, default=0):
    try:
        return float(valor) if valor is not None else default
    except (TypeError, ValueError):
        return default


def _pick_rate(entry):
    try:
        rate = float(entry.get("pr") if entry.get("pr") is not None else entry.get("pick_rate", 0))
    except (TypeError, ValueError):
        return 0.0
    if rate > 1:
        rate /= 100.0
    return max(0.0, min(1.0, rate))

def _resultado_vazio(heroi, modo, mensagem):
    vazio = mensagem or "Sem dados."
    return {
        "heroi": heroi, "perfil": modo, "start": vazio,
        "early": vazio, "mid": vazio, "late": vazio,
        "core": vazio, "alertas": [], "analise_matchup": "Sem análise de matchup disponível.", "fonte": "", "observacao": "",
    }
