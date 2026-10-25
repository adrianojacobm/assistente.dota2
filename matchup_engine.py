# -*- coding: utf-8 -*-
"""Build por função e análise de itens por matchup com partidas parseadas.

A saída inicial preserva compras úteis da base (exceto TP Scrolls). Nas outras
fases, componentes são reconstruídos em itens completos usando as receitas do
catálogo OpenDota; componentes consumidos por upgrades deixam de aparecer como
recomendações separadas.
"""
from collections import Counter, defaultdict
import math
import re
import statistics

import config
import opendota_client as api
import counter_engine
from hero_data import HERO_IDS, COMPONENTES_SOLTOS

FASES = ("start", "early", "mid", "late")
NOME_FASE = {"start": "Saída", "early": "Early", "mid": "Mid", "late": "Late"}

# Nomes/chaves alternativos do pergaminho de teleporte. Nunca é uma sugestão de build.
_TP_KEYS = {"tpscroll", "tp_scroll", "town_portal_scroll", "teleport_scroll", "teleportation_scroll"}
_TP_NAMES = {"town portal scroll", "teleport scroll", "teleportation scroll", "tp scroll"}

# Mesmo quando o catálogo o considera montável, Oblivion Staff é tratado como
# componente intermediário, não como recomendação final de build.
_INTERMEDIARIOS_OCULTOS = {"Oblivion Staff"}

# Itens base com função própria que podem ser comprados completos apesar de
# também servirem como componente de algum item situacional.
_ITENS_BASE_COMPLETOS = {
    "Blink Dagger", "Bottle", "Boots of Speed", "Boots of Travel", "Quelling Blade",
    "Magic Stick", "Magic Wand", "Infused Raindrops", "Dust of Appearance",
    "Smoke of Deceit", "Gem of True Sight", "Aghanim's Shard", "Aghanim's Blessing",
    "Refresher Shard", "Cheese", "Divine Rapier", "Hand of Midas",
}
_ITENS_WARD = {"Observer Ward", "Sentry Ward"}
_BOTAS_COMPLETAS = {"Power Treads", "Phase Boots", "Arcane Boots", "Tranquil Boots", "Boots of Travel", "Boots of Travel 2"}


def _int(valor, default=0):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


def _fase_tempo(tempo):
    # A Saída é o pacote comprado no pré-jogo (timestamp <= 0), não as compras
    # efetuadas durante os primeiros dois minutos de lane.
    if tempo <= 0:
        return "start"
    if tempo <= 600:
        return "early"
    if tempo <= 1500:
        return "mid"
    return "late"


def _eh_tp_scroll(nome, chave=""):
    chave_limpa = str(chave or "").lower().replace("item_", "")
    return chave_limpa in _TP_KEYS or str(nome or "").strip().lower() in _TP_NAMES


def _pro_match(detalhe, linha):
    """Exige lobby de torneio ou liga identificada na listagem/detalhe."""
    if not isinstance(detalhe, dict):
        return False
    lobby = _int(detalhe.get("lobby_type"), -1)
    return (
        lobby == 2
        or _int(detalhe.get("leagueid")) > 0
        or _int((linha or {}).get("leagueid")) > 0
        or bool((linha or {}).get("league_name"))
    )


def _rank_medio(linha=None, detalhe=None):
    for origem in (linha or {}, detalhe or {}):
        valor = _int(origem.get("average_rank"), 0)
        if valor > 0:
            return valor
    return 0


def _ranked_imortal(linha, detalhe):
    """Aceita somente ranked de alto nível; rank 80–85 corresponde a Imortal."""
    lobby_linha = _int((linha or {}).get("lobby_type"), -1)
    lobby_detalhe = _int((detalhe or {}).get("lobby_type"), -1)
    if 7 not in (lobby_linha, lobby_detalhe):
        return False
    if _rank_medio(linha, detalhe) >= config.MIN_RANKED_AVERAGE_TIER:
        return True

    jogadores = (detalhe or {}).get("players")
    ranks = []
    if isinstance(jogadores, list):
        for jogador in jogadores:
            if not isinstance(jogador, dict):
                continue
            rank = _int(jogador.get("rank_tier"), 0)
            if rank > 0:
                ranks.append(rank)
    # Alguns jogos não têm average_rank no resumo. Só os aceitamos se há dados
    # suficientes de jogadores e a mediana dos ranks conhecidos é Imortal.
    if len(ranks) >= 5:
        ranks.sort()
        mediana = ranks[len(ranks) // 2]
        return mediana >= config.MIN_RANKED_AVERAGE_TIER
    return False


def _partida_parseada_para_funcao(detalhe, hid, modo, chave_para_nome, id_para_nome, receitas):
    if not isinstance(detalhe, dict):
        return None
    jogadores = detalhe.get("players")
    if not isinstance(jogadores, list):
        return None
    nossos = [p for p in jogadores if isinstance(p, dict) and _int(p.get("hero_id")) == hid]
    if not nossos:
        return None
    jogador = nossos[0]
    nosso_time = _time_do_jogador(jogador)
    if not nosso_time:
        return None
    time_nosso = [p for p in jogadores if isinstance(p, dict) and _time_do_jogador(p) == nosso_time]
    time_inimigo = [p for p in jogadores if isinstance(p, dict) and _time_do_jogador(p) not in (None, nosso_time)]
    if not _modo_valido(jogador, time_nosso, modo):
        return None
    fases = _compras_por_fase(jogador, chave_para_nome, id_para_nome, receitas)
    if fases is None:
        return None
    inimigos_por_id = {_int(p.get("hero_id")): p for p in time_inimigo}
    return jogador, inimigos_por_id, fases


def _time_do_jogador(player):
    slot = _int(player.get("player_slot"), -1)
    return "radiant" if 0 <= slot < 128 else "dire" if slot >= 128 else None


def _rank_farm(player, jogadores_time):
    valores = [_int(p.get("gold_per_min"), 0) for p in jogadores_time]
    if not valores or max(valores) <= 0:
        return None
    gpms = [(_int(p.get("gold_per_min")), p) for p in jogadores_time]
    gpms.sort(key=lambda x: x[0], reverse=True)
    return next((i for i, (_, p) in enumerate(gpms) if p is player), None)


def _modo_valido(player, jogadores_time, modo):
    """Inferência conservadora da função com lane_role e posição de farm."""
    modo = modo.upper()
    lane_role = _int(player.get("lane_role"), 0)
    rank = _rank_farm(player, jogadores_time)
    if modo == "MID":
        return lane_role == 2
    if modo == "CARRY":
        return lane_role == 1 and (rank is None or rank <= 1)
    if modo == "SUP":
        if lane_role not in (1, 3):
            return False
        return rank is None or rank >= max(2, len(jogadores_time) - 3)
    return False


def _lane_opponent_valido(nosso_jogador, inimigo, modo):
    """Confirma que o herói selecionado como Lane 1/2 ocupava a lane oposta."""
    nossa_lane = _int(nosso_jogador.get("lane_role"), 0)
    lane_adv = _int(inimigo.get("lane_role"), 0)
    if modo == "MID":
        return nossa_lane == 2 and lane_adv == 2
    if modo == "CARRY":
        return nossa_lane == 1 and lane_adv == 3
    if modo == "SUP":
        return nossa_lane in (1, 3) and lane_adv == (3 if nossa_lane == 1 else 1)
    return False


def _consumir_componentes(inventario, componentes, permitir_faltantes=False):
    """Consome componentes; Boots of Speed é preservado como etapa de compra."""
    precisa = Counter(componentes)
    if not permitir_faltantes and any(len(inventario.get(nome, [])) < qtd for nome, qtd in precisa.items()):
        return False
    for nome, qtd in precisa.items():
        for _ in range(min(qtd, len(inventario.get(nome, [])))):
            token = inventario[nome].pop()
            registro = token.get("registro")
            if registro is not None and not registro.get("preservar_como_compra"):
                registro["consumido"] = True
    return True


def _fragmento_sem_funcao_propria(nome, nomes_componentes):
    if nome in COMPONENTES_SOLTOS:
        return True
    if nome in nomes_componentes and nome not in _ITENS_BASE_COMPLETOS:
        return True
    return False


def _compras_por_fase(player, chave_para_nome, id_para_nome, receitas=None):
    """Reconstrói compras por fase e preserva quantidades/tempos para análise.

    O pacote inicial usa exclusivamente compras com timestamp <= 0. A quantidade
    de itens é preservada em ``__start_items__``; as fases posteriores usam itens
    completos únicos por partida e guardam o tempo da primeira conclusão.
    """
    log = player.get("purchase_log")
    if not isinstance(log, list):
        return None
    if receitas is None:
        receitas = api.obter_catalogo_receitas_itens() or {}

    nomes_componentes = {
        comp for comps in receitas.values() for comp in comps
        if not str(comp).startswith("__RECIPE__:")
    }
    eventos = []
    for ordem, compra in enumerate(log):
        if not isinstance(compra, dict) or compra.get("time") is None:
            continue
        tempo = _int(compra.get("time"), -999999)
        if tempo == -999999:
            continue
        chave = compra.get("key") or compra.get("item") or ""
        chave_texto = str(chave)
        chave_lower = chave_texto.lower().removeprefix("item_")

        if chave_lower.startswith("recipe_"):
            alvo_key = chave_lower[len("recipe_"):]
            alvo_nome = chave_para_nome.get(alvo_key) or chave_para_nome.get(f"item_{alvo_key}")
            if alvo_nome and alvo_nome in receitas:
                eventos.append((tempo, ordem, _fase_tempo(tempo), f"__RECIPE__:{alvo_nome}", chave_texto))
            continue

        nome = None
        if compra.get("item_id") is not None:
            nome = id_para_nome.get(_int(compra.get("item_id")))
        if not nome and chave:
            chave_limpa = chave_texto.removeprefix("item_")
            nome = chave_para_nome.get(chave_limpa) or chave_para_nome.get(chave_texto)
        if not nome or nome == "Recipe" or _eh_tp_scroll(nome, chave):
            continue
        if nome in _ITENS_WARD:
            continue
        fase = _fase_tempo(tempo)
        if nome == "Boots of Travel 2" and fase in ("start", "early", "mid"):
            fase = "late"
        eventos.append((tempo, ordem, fase, nome, chave_texto))
    eventos.sort(key=lambda e: (e[0], e[1]))

    compostos_explicitos = {nome for _, _, _, nome, _ in eventos if nome in receitas}
    inventario = defaultdict(list)
    registros = []
    saida = {fase: set() for fase in FASES}
    itens_saida_crus = []

    def adicionar_token(nome, fase, completo, tempo, ordem):
        registro = None
        if completo:
            registro = {
                "nome": nome,
                "fase": fase,
                "tempo": int(tempo),
                "ordem": int(ordem),
                "consumido": False,
                "oculto": nome in _INTERMEDIARIOS_OCULTOS,
                "preservar_como_compra": nome == "Boots of Speed",
            }
            registros.append(registro)
        inventario[nome].append({"registro": registro})

    def montar_receitas(fase_atual, tempo_atual, ordem_atual):
        mudou = True
        while mudou:
            mudou = False
            candidatas = sorted(
                ((nome, comps) for nome, comps in receitas.items() if nome not in compostos_explicitos),
                key=lambda p: (len(p[1]), p[0]),
            )
            for nome_item, componentes in candidatas:
                if not componentes:
                    continue
                reais = [c for c in componentes if not str(c).startswith("__RECIPE__:")]
                exige_receita = any(str(c).startswith("__RECIPE__:") for c in componentes)
                if len(reais) <= 1 and not exige_receita:
                    continue
                if _consumir_componentes(inventario, componentes):
                    adicionar_token(nome_item, fase_atual, completo=True, tempo=tempo_atual, ordem=ordem_atual)
                    mudou = True
                    break

    for tempo, ordem, fase, nome, chave in eventos:
        if str(nome).startswith("__RECIPE__:"):
            inventario[nome].append({"registro": None})
            montar_receitas(fase, tempo, ordem)
            continue

        if fase == "start":
            # Guarda cada unidade comprada, mesmo que haja três do mesmo item.
            itens_saida_crus.append({"nome": nome, "tempo": tempo, "ordem": ordem})
            saida["start"].add(nome)

        if nome in receitas:
            _consumir_componentes(inventario, receitas[nome], permitir_faltantes=True)
            adicionar_token(nome, fase, completo=True, tempo=tempo, ordem=ordem)
            montar_receitas(fase, tempo, ordem)
            continue

        fragmento = _fragmento_sem_funcao_propria(nome, nomes_componentes)
        adicionar_token(nome, fase, completo=not fragmento, tempo=tempo, ordem=ordem)
        montar_receitas(fase, tempo, ordem)

    tempos_por_fase = {fase: {} for fase in FASES}
    for reg in registros:
        if reg["consumido"] or reg["oculto"] or reg["fase"] == "start":
            continue
        fase = reg["fase"]
        saida[fase].add(reg["nome"])
        anterior = tempos_por_fase[fase].get(reg["nome"])
        momento = (reg["tempo"], reg["ordem"])
        if anterior is None or momento < anterior:
            tempos_por_fase[fase][reg["nome"]] = momento

    if not any(saida[fase] for fase in FASES) and not itens_saida_crus:
        return None
    return {
        **saida,
        "__start_items__": itens_saida_crus,
        "__tempos__": tempos_por_fase,
    }


def _chave_item_exibido(nome):
    """Retira sufixo de quantidade para deduplicar, sem apagar a quantidade visual."""
    return re.sub(r"\s*[x×]\s*\d+\s*$", "", str(nome).strip(), flags=re.IGNORECASE).strip().casefold()


def _pacote_saida_valido(eventos, precos):
    """Retorna bundle inicial ordenado e custo, rejeitando pacote acima de 600 ouro."""
    if not eventos:
        return None
    nomes = [str(ev.get("nome", "")).strip() for ev in sorted(eventos, key=lambda e: (e.get("tempo", 0), e.get("ordem", 0))) if ev.get("nome")]
    if not nomes:
        return None
    custo_total = 0
    for nome in nomes:
        if nome not in precos:
            return None  # sem preço confirmado, não podemos garantir o teto do orçamento
        custo = precos[nome]
        if custo < 0:
            return None
        custo_total += custo
    if custo_total > config.ORCAMENTO_SAIDA_INICIAL:
        return None
    return tuple(nomes), custo_total


def _formatar_pacote_saida(nomes):
    """Agrupa unidades repetidas (por exemplo, Gauntlets of Strength ×3)."""
    contagem = Counter(nomes)
    primeiras = {}
    for indice, nome in enumerate(nomes):
        primeiras.setdefault(nome, indice)
    ordenados = sorted(contagem, key=lambda n: primeiras[n])
    return [f"{nome} ×{contagem[nome]}" if contagem[nome] > 1 else nome for nome in ordenados]


def _percentual(quantidade, total):
    return (100.0 * quantidade / total) if total else 0.0


def _construir_fases_core(contagens, tempos, n_jogos):
    """Seleciona itens realmente core e os ordena pela mediana de compra/conclusão."""
    resultado = {fase: [] for fase in FASES}
    percentuais = {}
    situacionais = []
    for fase in ("early", "mid", "late"):
        candidatos = []
        for nome, quantidade in contagens[fase].items():
            percentual = _percentual(quantidade, n_jogos)
            if (nome in COMPONENTES_SOLTOS or nome in _INTERMEDIARIOS_OCULTOS or
                    nome in _ITENS_WARD or _eh_tp_scroll(nome)):
                continue
            percentuais[(fase, nome)] = percentual
            momentos = tempos[fase].get(nome, [])
            mediana = statistics.median(momentos) if momentos else {"early": 300, "mid": 900, "late": 1800}[fase]
            item = {"nome": nome, "percentual": percentual, "mediana": mediana, "contagem": quantidade}
            if percentual >= config.PERCENTUAL_CORE_ITEM * 100:
                candidatos.append(item)
            elif percentual >= config.MIN_PERCENTUAL_SITUACIONAL * 100:
                situacionais.append({**item, "fase": fase})
        candidatos.sort(key=lambda item: (item["mediana"], -item["percentual"], item["nome"]))
        # Bota marrom é uma etapa própria e precisa anteceder a bota completa.
        if "Boots of Speed" in [it["nome"] for it in candidatos]:
            botas = next(it for it in candidatos if it["nome"] == "Boots of Speed")
            candidatos.remove(botas)
            idx = next((i for i, it in enumerate(candidatos) if it["nome"] in _BOTAS_COMPLETAS), len(candidatos))
            candidatos.insert(idx, botas)
        maximo = {"early": 8, "mid": 8, "late": 8}[fase]
        resultado[fase] = [it["nome"] for it in candidatos[:maximo]]
    situacionais.sort(key=lambda it: (-it["percentual"], it["mediana"], it["nome"]))
    return resultado, percentuais, situacionais


def deduplicar_fases(itens_por_fase):
    """Deduplica itens inclusive quando a Saída apresenta quantidades (×3)."""
    resultado = {}
    vistos = set()
    for fase in FASES:
        itens = list(itens_por_fase.get(fase, []) or [])
        itens = [str(item).strip() for item in itens if str(item).strip()]
        if "Boots of Speed" in itens:
            itens.remove("Boots of Speed")
            posicao = next((i for i, item in enumerate(itens) if item in _BOTAS_COMPLETAS), len(itens))
            itens.insert(posicao, "Boots of Speed")
        limpos = []
        for item in itens:
            chave = _chave_item_exibido(item)
            if chave and chave not in vistos:
                limpos.append(item)
                vistos.add(chave)
        resultado[fase] = limpos
    return resultado

def _montar_resultado_vazio(texto):
    return {
        "itens_funcao": {},
        "itens_saida_lane": [],
        "itens_early_lane": [],
        "itens_situacionais": [],
        "opcoes": [],
        "opcoes_detalhes": [],
        "amostra_funcao": 0,
        "texto": texto,
    }


def _linha_pode_ser_pro(linha):
    return (
        _int((linha or {}).get("leagueid")) > 0
        or bool((linha or {}).get("league_name"))
        or _int((linha or {}).get("lobby_type"), -1) == 2
    )


def _coletar_build_profissional(hid, modo, chave_para_nome, id_para_nome, receitas, precos):
    """Percorre páginas recentes até obter 100 partidas profissionais parseadas da função."""
    amostras = []
    vistos = set()
    offset = 0
    total_varrido = 0
    pagina = config.TAMANHO_PAGINA_PARTIDAS_HEROI
    maximo = config.MAX_HISTORICO_HEROI_SCAN
    while len(amostras) < config.PARTIDAS_PRO_POR_BUILD and total_varrido < maximo:
        resposta = api.obter_partidas_heroi(hid, limit=pagina, offset=offset) or []
        if not isinstance(resposta, list) or not resposta:
            break
        tamanho_resposta = len(resposta)
        linhas = [m for m in resposta if isinstance(m, dict) and _int(m.get("match_id"))]
        linhas.sort(key=lambda m: _int(m.get("start_time")), reverse=True)
        vistos_antes = len(vistos)
        for linha in linhas:
            total_varrido += 1
            match_id = _int(linha.get("match_id"))
            if not match_id or match_id in vistos:
                continue
            vistos.add(match_id)
            if not _linha_pode_ser_pro(linha):
                continue
            detalhe = api.obter_detalhes_partida(match_id)
            if not _pro_match(detalhe, linha):
                continue
            extraido = _partida_parseada_para_funcao(
                detalhe, hid, modo, chave_para_nome, id_para_nome, receitas
            )
            if not extraido:
                continue
            jogador, inimigos, fases = extraido
            pacote_saida = _pacote_saida_valido(fases.get("__start_items__", []), precos)
            amostras.append({
                "match_id": match_id,
                "start_time": _int(linha.get("start_time")),
                "fases": fases,
                "pacote_saida": pacote_saida,
                "inimigos": inimigos,
            })
            if len(amostras) >= config.PARTIDAS_PRO_POR_BUILD:
                break
        # Algumas versões/implantações do endpoint de partidas de herói não
        # respeitam offset. Não repetimos a mesma página milhares de vezes.
        if len(vistos) == vistos_antes or tamanho_resposta < pagina or total_varrido >= maximo:
            break
        offset += pagina
    # API retorna normalmente mais recentes primeiro, mas ordena a amostra final
    # explicitamente para manter a seleção determinística.
    amostras.sort(key=lambda m: m["start_time"], reverse=True)
    return amostras, total_varrido


def analisar_build_e_matchup(heroi: str, modo: str, adversarios: list[str], adversarios_lane=None,
                             ameaca: str | None = None) -> dict:
    """Build principal das últimas 100 partidas profissionais parseadas por função.

    Counters na área Opções são recomendações contextuais por heróis selecionados e
    função, não itens inferidos a partir de uma ou duas partidas particulares.
    """
    hid = HERO_IDS.get(heroi)
    modo = modo.upper() if modo else "CARRY"
    if modo not in ("CARRY", "MID", "SUP"):
        modo = "CARRY"
    alvos = list(dict.fromkeys(a for a in (adversarios or []) if a and a != "Nenhum" and a in HERO_IDS))
    lane_alvos = list(dict.fromkeys(a for a in (adversarios_lane or []) if a and a != "Nenhum" and a in alvos))
    ameaca = ameaca if ameaca in alvos else None
    if not hid:
        return _montar_resultado_vazio("Herói não encontrado para análise de partidas.")

    # Os endpoints de constantes usam o mesmo cache; não são quatro requisições diferentes.
    id_para_nome = api.obter_catalogo_itens() or {}
    chave_para_nome = api.obter_catalogo_chaves_itens() or {}
    receitas = api.obter_catalogo_receitas_itens() or {}
    precos = api.obter_catalogo_precos_itens() or {}
    if not id_para_nome or not chave_para_nome:
        return _montar_resultado_vazio("Não foi possível carregar o catálogo de itens da OpenDota. Confira a conexão.")

    amostras, total_varrido = _coletar_build_profissional(
        hid, modo, chave_para_nome, id_para_nome, receitas, precos
    )
    n_funcao = len(amostras)
    if not n_funcao:
        return _montar_resultado_vazio(
            f"Nenhuma partida profissional parseada e confirmada para {heroi} na função {modo}. "
            f"Foram percorridas {total_varrido} partidas recentes do herói."
        )

    contagens = {fase: Counter() for fase in FASES}
    tempos = {fase: defaultdict(list) for fase in FASES}
    pacotes_saida = Counter()
    ordem_pacotes_saida = defaultdict(Counter)
    custo_pacote = {}
    jogos_com_saida_valida = 0
    ids_amostra = []
    for jogo in amostras:
        ids_amostra.append(jogo["match_id"])
        fases = jogo["fases"]
        for fase in ("early", "mid", "late"):
            for nome in fases.get(fase, set()):
                contagens[fase][nome] += 1  # no máximo uma ocorrência por jogo
                momento = (fases.get("__tempos__", {}).get(fase, {}) or {}).get(nome)
                if momento:
                    tempos[fase][nome].append(int(momento[0]))
        pacote = jogo.get("pacote_saida")
        if pacote:
            nomes, custo = pacote
            chave_bundle = tuple(sorted(Counter(nomes).items()))
            pacotes_saida[chave_bundle] += 1
            ordem_pacotes_saida[chave_bundle][tuple(nomes)] += 1
            custo_pacote[chave_bundle] = custo
            jogos_com_saida_valida += 1

    itens_funcao, percentuais, situacionais = _construir_fases_core(contagens, tempos, n_funcao)
    itens_funcao["start"] = []
    pacote_linha = None
    pct_pacote = 0.0
    n_bundle = 0
    if pacotes_saida:
        chave_vencedora, n_bundle = max(pacotes_saida.items(), key=lambda p: (p[1], tuple(p[0])))
        ordem_vencedora = max(ordem_pacotes_saida[chave_vencedora].items(), key=lambda p: (p[1], p[0]))[0]
        itens_funcao["start"] = _formatar_pacote_saida(ordem_vencedora)
        pct_pacote = _percentual(n_bundle, n_funcao)
        pacote_linha = (ordem_vencedora, custo_pacote[chave_vencedora])

    # Recomendações por ameaça e lane vêm de regras de counter separadas da build core.
    opcoes, opcoes_detalhes = counter_engine.recomendar_itens_counter(
        lane_alvos=lane_alvos, ameaca=ameaca, modo=modo
    )
    core_names = {
        _chave_item_exibido(nome)
        for fase in ("start", "early", "mid", "late")
        for nome in itens_funcao.get(fase, [])
    }
    opcoes = [nome for nome in opcoes if _chave_item_exibido(nome) not in core_names]

    linhas = [
        f"📊 BUILD POR FUNÇÃO — {heroi} / {modo}",
        f"Amostra: {n_funcao}/{config.PARTIDAS_PRO_POR_BUILD} partidas profissionais parseadas mais recentes; "
        f"{total_varrido} partidas do histórico do herói foram percorridas.",
    ]
    if pacote_linha:
        linhas.append(
            f"Saída mais comum válida: {', '.join(itens_funcao['start'])} "
            f"({n_bundle}/{n_funcao} jogos = {pct_pacote:.1f}%; custo catalogado {pacote_linha[1]}/{config.ORCAMENTO_SAIDA_INICIAL} ouro)."
        )
    else:
        linhas.append(
            f"Saída: nenhum pacote inicial pôde ser confirmado dentro de {config.ORCAMENTO_SAIDA_INICIAL} ouro "
            "com os preços do catálogo atual; não foi criada uma combinação artificial."
        )
    linhas.append(f"Jogos com pacote inicial válido: {jogos_com_saida_valida}/{n_funcao}.")

    fase_rotulos = {"early": "EARLY", "mid": "MID", "late": "LATE"}
    for fase in ("early", "mid", "late"):
        lista = itens_funcao.get(fase, [])
        if lista:
            detalhes = [f"{nome} ({percentuais.get((fase, nome), 0):.0f}%; mediana {_tempo_para_minuto(tempos[fase].get(nome, []))})" for nome in lista]
            linhas.append(f"{fase_rotulos[fase]} core (≥{config.PERCENTUAL_CORE_ITEM*100:.0f}%): " + ", ".join(detalhes))
        else:
            linhas.append(f"{fase_rotulos[fase]}: nenhum item atingiu o corte de core de {config.PERCENTUAL_CORE_ITEM*100:.0f}% nesta amostra.")

    if situacionais:
        linhas.append("Situacionais abaixo do corte de core: " + "; ".join(
            f"{item['nome']} ({fase_rotulos[item['fase']]} {item['percentual']:.0f}%)"
            for item in situacionais[:15]
        ))
    if opcoes_detalhes:
        linhas.append("OPÇÕES DE COUNTER — adaptadas à função selecionada:")
        linhas.extend(f"• {linha}" for linha in opcoes_detalhes)
    elif alvos:
        linhas.append("Não há sugestão de counter específica para os inimigos escolhidos nesta versão; a build core não foi alterada.")
    else:
        linhas.append("Selecione Lane 1, Lane 2 e/ou Ameaça para preencher Opções com counters contextuais.")

    linhas.append("Fonte: OpenDota /heroes/{id}/matches + /matches/{id}/purchase_log. Só partidas pro/torneio são usadas para a build principal.")
    linhas.append("Core = item comprado em pelo menos metade das partidas parseadas da função; itens menos frequentes ficam como situacionais, fora da progressão fixa.")
    return {
        "itens_funcao": itens_funcao,
        "itens_saida_lane": [],
        "itens_early_lane": [],
        "itens_situacionais": situacionais,
        "opcoes": list(dict.fromkeys(opcoes)),
        "opcoes_detalhes": opcoes_detalhes,
        "amostra_funcao": n_funcao,
        "texto": "\n".join(linhas),
    }


def _tempo_para_minuto(tempos):
    if not tempos:
        return "--"
    mediana = statistics.median(tempos)
    return f"{int(mediana) // 60}:{int(mediana) % 60:02d}"

def analisar_itens_matchup(heroi: str, modo: str, adversarios: list[str], adversarios_lane=None,
                           ameaca: str | None = None) -> str:
    """Wrapper compatível para quem só precisa da análise textual de matchup."""
    return analisar_build_e_matchup(heroi, modo, adversarios, adversarios_lane, ameaca).get("texto", "Sem análise.")
