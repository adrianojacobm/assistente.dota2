# -*- coding: utf-8 -*-
"""Counter-picks usando os resultados agregados reais da OpenDota."""
import config
import opendota_client as api
from hero_data import HERO_IDS, ID_PARA_HEROI


# `roles` da OpenDota são arquétipos do herói, não posição de lane.
# MID aceita os arquétipos que comumente ocupam mid; SUP exige Support.
# Isto é um filtro aproximado, não uma classificação pro de posição 1-5.
_ROLES_POR_MODO = {
    "CARRY": {"Carry"},
    "MID": {"Carry", "Nuker"},
    "OFFLANE": {"Carry", "Nuker", "Initiator", "Durable", "Disabler"},
    "SUP": {"Support"},
}


def _win_rate_meta(hero_stats_lista: list) -> dict:
    saida = {}
    for h in hero_stats_lista or []:
        hid = h.get("id")
        if hid is None:
            continue
        picks = _int(h.get("7_pick")) + _int(h.get("8_pick")) + _int(h.get("pro_pick"))
        wins = _int(h.get("7_win")) + _int(h.get("8_win")) + _int(h.get("pro_win"))
        saida[hid] = (wins / picks) if picks > 0 else 0.50
    return saida


def _int(valor):
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def calcular_counter_picks(lane1: str, lane2: str, ameaca: str, modo: str, catalogo_heroes: dict) -> str:
    modo = modo if modo in _ROLES_POR_MODO else "CARRY"
    alvos = list(dict.fromkeys(a for a in (lane1, lane2, ameaca) if a and a != "Nenhum"))
    if not alvos:
        return "Selecione pelo menos 1 inimigo (Lane 1/2 ou Ameaça) para calcular counter-picks."

    wr_meta = _win_rate_meta(api.obter_hero_stats())
    placar = {}  # hero_id -> [wins ponderadas, jogos ponderados, jogos sem peso]

    for inimigo in alvos:
        ini_id = HERO_IDS.get(inimigo)
        if not ini_id:
            continue
        matchups = api.obter_matchups(ini_id) or []
        peso_alvo = 1.5 if inimigo == ameaca else 1.0
        for m in matchups:
            if not isinstance(m, dict):
                continue
            hid = _int(m.get("hero_id"))
            jogos = _int(m.get("games_played"))
            vitorias_inimigo = _int(m.get("wins"))
            if jogos < config.MIN_JOGOS_MATCHUP or hid not in ID_PARA_HEROI:
                continue
            # Na resposta /heroes/{id}/matchups, `wins` corresponde ao herói do
            # endpoint (o inimigo selecionado); invertemos para obter o win rate
            # do candidato contra ele. A agregação é ponderada por jogos reais.
            vitorias_candidato = max(0, jogos - vitorias_inimigo)
            entrada = placar.setdefault(hid, [0.0, 0.0, 0])
            entrada[0] += vitorias_candidato * peso_alvo
            entrada[1] += jogos * peso_alvo
            entrada[2] += jogos

    if not placar:
        return "Sem dados suficientes de matchup retornados pela OpenDota para esses heróis."

    roles_aceitas = _ROLES_POR_MODO[modo]
    ranking = []
    for hid, (wins_pond, jogos_pond, total_jogos) in placar.items():
        roles = set(catalogo_heroes.get(hid, {}).get("roles", []) or [])
        if roles and not roles.intersection(roles_aceitas):
            continue
        if jogos_pond <= 0:
            continue
        wr_confronto = (wins_pond / jogos_pond) * 100
        wr_m = wr_meta.get(hid, 0.50) * 100
        score = (wr_confronto * 0.7) + (wr_m * 0.3)
        ranking.append((ID_PARA_HEROI[hid], wr_confronto, wr_m, total_jogos, score))

    ranking.sort(key=lambda x: x[4], reverse=True)
    top = ranking[:6]
    if not top:
        return f"Sem heróis do arquétipo apropriado para '{modo}' com amostra suficiente contra esses alvos."

    linhas = [f"🎯 TOP PICKS ({modo}) — matchup agregado + meta atual:"]
    for nome, wr_vs, wr_m, jogos, _ in top:
        linhas.append(f"• {nome:<18} | vs alvos: {wr_vs:4.1f}% | meta geral: {wr_m:4.1f}% ({jogos} jogos)")
    linhas.append("Nota: roles da OpenDota são arquétipos; o filtro MID é aproximado, não lane_role por partida.")
    return "\n".join(linhas)


# Heurísticas de itens situacionais para a secção Opções. A build core nunca é
# alterada por estas regras: são sugestões independentes, filtradas pela função.
_TAGS_COUNTER = {
    "evasion": {
        "Monkey King Bar": "true strike contra evasão",
        "Bloodthorn": "true strike/controle de alvo durante o ativo",
        "Ghost Scepter": "evita ataques físicos por alguns segundos",
        "Force Staff": "cria distância contra o salto/avanço",
        "Glimmer Cape": "proteção e resistência mágica durante a fuga",
        "Aeon Disk": "sobrevivência contra burst",
    },
    "illusion": {
        "Battle Fury": "dano em área e cleave contra ilusões",
        "Mjollnir": "dano em área/efeito contra muitos ataques",
        "Gleipnir": "controle em área para manter ilusões agrupadas",
        "Shiva's Guard": "dano em área e redução de velocidade de ataque",
        "Crimson Guard": "mitigação de ataques físicos de unidades",
    },
    "sustain": {
        "Spirit Vessel": "reduz cura e regeneração",
        "Eye of Skadi": "reduz cura e sustain de alvos atingidos",
        "Shiva's Guard": "reduz regeneração e fornece dano em área",
        "Nullifier": "remove buffs importantes e dificulta a fuga",
        "Solar Crest": "redução de armadura/apoio ao foco da equipe",
    },
    "magic_burst": {
        "Black King Bar": "resistência/ imunidade a grande parte do controle mágico",
        "Mage Slayer": "reduz dano mágico recebido de heróis atingidos",
        "Glimmer Cape": "resistência mágica e reposicionamento",
        "Pipe of Insight": "barreira mágica para a equipe",
        "Aeon Disk": "proteção contra dano explosivo",
    },
    "mobile": {
        "Orchid Malevolence": "silêncio contra heróis dependentes de habilidades",
        "Bloodthorn": "silêncio e foco em alvo móvel",
        "Scythe of Vyse": "controle forte para impedir escape",
        "Gleipnir": "root em área para travar mobilidade",
        "Eul's Scepter of Divinity": "desarme temporário/reconfiguração da luta",
        "Force Staff": "reposicionamento defensivo",
    },
    "physical": {
        "Heaven's Halberd": "desarmar um atacante físico",
        "Assault Cuirass": "armadura e redução de armadura para lutas físicas",
        "Ghost Scepter": "evita ataques físicos durante o efeito",
        "Force Staff": "cria distância do atacante",
        "Aeon Disk": "reduz o risco de ser eliminado em burst",
    },
    "single_target": {
        "Linken's Sphere": "bloqueia uma habilidade unit-target",
        "Lotus Orb": "dispela e pode refletir habilidades unit-target",
        "Aeon Disk": "sobrevivência contra iniciação explosiva",
        "Force Staff": "ajuda a sair do alcance/posicionamento ruim",
    },
    "invisible": {
        "Dust of Appearance": "revelação temporária de invisíveis",
        "Gem of True Sight": "detecção contínua carregada pela equipe",
    },
    "mana_burn": {
        "Orchid Malevolence": "silêncio antes que o alvo use mobilidade",
        "Scythe of Vyse": "controle longo sobre herói móvel",
        "Black King Bar": "mitiga parte do controle mágico durante a janela ativa",
    },
}

_ITENS_POR_TAG_E_FUNCAO = {
    "CARRY": {
        "evasion": ["Monkey King Bar", "Bloodthorn"],
        "illusion": ["Battle Fury", "Mjollnir", "Gleipnir", "Shiva's Guard"],
        "sustain": ["Eye of Skadi", "Nullifier", "Silver Edge"],
        "magic_burst": ["Black King Bar", "Mage Slayer"],
        "mobile": ["Orchid Malevolence", "Scythe of Vyse", "Bloodthorn", "Gleipnir"],
        "physical": ["Heaven's Halberd", "Assault Cuirass", "Eye of Skadi"],
        "single_target": ["Linken's Sphere", "Black King Bar"],
        "invisible": ["Dust of Appearance", "Gem of True Sight"],
        "mana_burn": ["Orchid Malevolence", "Scythe of Vyse"],
    },
    "MID": {
        "evasion": ["Monkey King Bar", "Bloodthorn"],
        "illusion": ["Mjollnir", "Gleipnir", "Shiva's Guard"],
        "sustain": ["Spirit Vessel", "Eye of Skadi", "Shiva's Guard", "Nullifier"],
        "magic_burst": ["Black King Bar", "Mage Slayer"],
        "mobile": ["Orchid Malevolence", "Scythe of Vyse", "Bloodthorn", "Gleipnir"],
        "physical": ["Heaven's Halberd", "Shiva's Guard", "Assault Cuirass"],
        "single_target": ["Linken's Sphere", "Black King Bar"],
        "invisible": ["Dust of Appearance", "Gem of True Sight"],
        "mana_burn": ["Orchid Malevolence", "Scythe of Vyse"],
    },
    "SUP": {
        "evasion": ["Ghost Scepter", "Force Staff", "Glimmer Cape", "Aeon Disk"],
        "illusion": ["Crimson Guard", "Shiva's Guard", "Gleipnir", "Force Staff"],
        "sustain": ["Spirit Vessel", "Solar Crest", "Eul's Scepter of Divinity"],
        "magic_burst": ["Glimmer Cape", "Pipe of Insight", "Aeon Disk", "Pavise"],
        "mobile": ["Eul's Scepter of Divinity", "Force Staff", "Glimmer Cape", "Scythe of Vyse"],
        "physical": ["Ghost Scepter", "Force Staff", "Aeon Disk", "Glimmer Cape"],
        "single_target": ["Lotus Orb", "Aeon Disk", "Force Staff", "Glimmer Cape"],
        "invisible": ["Dust of Appearance", "Gem of True Sight"],
        "mana_burn": ["Force Staff", "Aeon Disk", "Eul's Scepter of Divinity"],
    },
}

# Offlane é uma posição própria: parte das respostas de utilidade do mid se aplica,
# mas ameaças físicas recebem respostas específicas de frontliner quando cadastradas.
_ITENS_POR_TAG_E_FUNCAO["OFFLANE"] = {
    tag: list(itens) for tag, itens in _ITENS_POR_TAG_E_FUNCAO["MID"].items()
}
_ITENS_POR_TAG_E_FUNCAO["OFFLANE"]["physical"] = ["Heaven's Halberd", "Shiva's Guard", "Ghost Scepter"]

_TAGS_HEROIS = {
    # Evasão ou ameaça de ataques físicos críticos
    "Phantom Assassin": {"evasion", "physical"},
    "Templar Assassin": {"evasion", "physical"},
    "Windranger": {"evasion", "physical", "mobile"},
    "Riki": {"evasion", "physical", "invisible"},
    "Troll Warlord": {"physical"}, "Ursa": {"physical"}, "Sven": {"physical"},
    "Juggernaut": {"physical"}, "Slark": {"physical", "mobile"}, "Drow Ranger": {"physical"},
    "Sniper": {"physical"}, "Clinkz": {"physical", "invisible"}, "Wraith King": {"physical", "sustain"},
    "Lifestealer": {"physical", "sustain"}, "Legion Commander": {"physical", "single_target"},
    "Faceless Void": {"physical", "mobile"}, "Monkey King": {"physical"},
    # Ilusões/unidades
    "Phantom Lancer": {"illusion", "mobile"}, "Naga Siren": {"illusion"},
    "Chaos Knight": {"illusion", "physical"}, "Terrorblade": {"illusion", "physical"},
    "Meepo": {"illusion"},
    # Sustentação, cura ou regeneração elevada
    "Huskar": {"sustain", "physical"}, "Necrophos": {"sustain", "magic_burst"},
    "Bristleback": {"sustain", "physical"}, "Alchemist": {"sustain", "physical"},
    "Morphling": {"sustain", "mobile"}, "Timbersaw": {"sustain"}, "Abaddon": {"sustain"},
    "Dazzle": {"sustain"}, "Oracle": {"sustain"}, "Omniknight": {"sustain"},
    "Undying": {"sustain"}, "Warlock": {"sustain"},
    # Burst mágico
    "Zeus": {"magic_burst"}, "Lina": {"magic_burst"}, "Skywrath Mage": {"magic_burst"},
    "Pugna": {"magic_burst"}, "Leshrac": {"magic_burst"}, "Tinker": {"magic_burst"},
    "Invoker": {"magic_burst"}, "Queen of Pain": {"magic_burst", "mobile"},
    "Lion": {"magic_burst", "single_target"}, "Shadow Shaman": {"single_target"},
    "Nyx Assassin": {"magic_burst", "invisible"}, "Jakiro": {"magic_burst"},
    # Mobilidade e escape
    "Storm Spirit": {"mobile", "magic_burst"}, "Puck": {"mobile", "magic_burst"},
    "Ember Spirit": {"mobile", "magic_burst"}, "Void Spirit": {"mobile", "magic_burst"},
    "Weaver": {"mobile", "invisible", "physical"}, "Bounty Hunter": {"invisible"},
    "Nature's Prophet": {"mobile"}, "Anti-Mage": {"mobile", "mana_burn"},
    # Iniciação/controle unit-target
    "Doom": {"single_target"}, "Batrider": {"single_target", "magic_burst"},
    "Beastmaster": {"single_target"}, "Vengeful Spirit": {"single_target"},
    "Pudge": {"single_target"}, "Magnus": {"single_target"},
}

# Contra PA, por exemplo, suporte recebe itens defensivos; MKB fica para uma core.
_ITENS_ESPECIFICOS = {
    "Phantom Assassin": {
        "CARRY": ["Monkey King Bar", "Bloodthorn"],
        "MID": ["Monkey King Bar", "Bloodthorn"],
        "OFFLANE": ["Heaven's Halberd", "Shiva's Guard", "Ghost Scepter"],
        "SUP": ["Ghost Scepter", "Force Staff", "Glimmer Cape", "Aeon Disk"],
    },
    "Riki": {
        "CARRY": ["Monkey King Bar", "Dust of Appearance", "Gem of True Sight"],
        "MID": ["Monkey King Bar", "Dust of Appearance", "Gem of True Sight"],
        "SUP": ["Dust of Appearance", "Ghost Scepter", "Force Staff", "Glimmer Cape"],
    },
    "Phantom Lancer": {
        "CARRY": ["Battle Fury", "Mjollnir", "Gleipnir"],
        "MID": ["Mjollnir", "Gleipnir", "Shiva's Guard"],
        "SUP": ["Crimson Guard", "Shiva's Guard", "Gleipnir"],
    },
    "Huskar": {
        "CARRY": ["Eye of Skadi", "Nullifier", "Silver Edge"],
        "MID": ["Spirit Vessel", "Eye of Skadi", "Shiva's Guard"],
        "SUP": ["Spirit Vessel", "Solar Crest", "Eul's Scepter of Divinity"],
    },
    "Bristleback": {
        "CARRY": ["Silver Edge", "Eye of Skadi", "Nullifier"],
        "MID": ["Silver Edge", "Spirit Vessel", "Shiva's Guard"],
        "SUP": ["Spirit Vessel", "Solar Crest", "Eul's Scepter of Divinity"],
    },
    "Anti-Mage": {
        "CARRY": ["Orchid Malevolence", "Scythe of Vyse", "Bloodthorn"],
        "MID": ["Orchid Malevolence", "Scythe of Vyse", "Bloodthorn"],
        "SUP": ["Force Staff", "Glimmer Cape", "Aeon Disk", "Eul's Scepter of Divinity"],
    },
    "Doom": {
        "CARRY": ["Linken's Sphere", "Black King Bar"],
        "MID": ["Linken's Sphere", "Black King Bar"],
        "SUP": ["Lotus Orb", "Aeon Disk", "Force Staff"],
    },
    "Legion Commander": {
        "CARRY": ["Linken's Sphere", "Black King Bar"],
        "MID": ["Linken's Sphere", "Black King Bar"],
        "SUP": ["Lotus Orb", "Ghost Scepter", "Force Staff"],
    },
}

_EARLY_LANE_MAGIC = {
    "Zeus", "Lina", "Skywrath Mage", "Pugna", "Leshrac", "Tinker", "Necrophos",
    "Batrider", "Jakiro", "Venomancer", "Invoker", "Queen of Pain", "Shadow Fiend",
}
_EARLY_LANE_PHYSICAL = {
    "Phantom Assassin", "Ursa", "Troll Warlord", "Sven", "Juggernaut", "Drow Ranger",
    "Slardar", "Wraith King", "Clinkz", "Legion Commander", "Riki",
}
_EARLY_LANE_SUSTAIN = {"Huskar", "Bristleback", "Necrophos", "Alchemist", "Morphling", "Abaddon", "Dazzle", "Oracle"}
_EARLY_LANE_INVIS = {"Riki", "Clinkz", "Bounty Hunter", "Nyx Assassin", "Weaver"}


def recomendar_itens_counter(lane_alvos=None, ameaca=None, modo="CARRY"):
    """Gera counters genéricos por inimigo, função e etapa (lane/jogo).

    Retorna (itens_para_overlay, explicações_para_painel). A build principal por
    frequência profissional não depende desta recomendação situacional.
    """
    modo = str(modo or "CARRY").upper()
    if modo not in _ITENS_POR_TAG_E_FUNCAO:
        modo = "CARRY"
    lane_alvos = list(dict.fromkeys(h for h in (lane_alvos or []) if h and h != "Nenhum"))
    alvos = list(lane_alvos)
    if ameaca and ameaca != "Nenhum" and ameaca not in alvos:
        alvos.append(ameaca)

    ranking = {}
    detalhes = []

    def adicionar(nome, peso, motivo):
        if not nome:
            return
        ranking[nome] = max(ranking.get(nome, 0), peso)
        detalhes.append((peso, f"{nome}: {motivo}"))

    for inimigo in lane_alvos:
        # Lane: itens baratos de resposta imediata quando a habilidade do inimigo justifica.
        if inimigo in _EARLY_LANE_MAGIC:
            adicionar("Magic Stick", 100, f"lane contra {inimigo}: cargas a partir de habilidades frequentes")
            adicionar("Infused Raindrops", 95, f"lane contra {inimigo}: mitigação de dano mágico de alvo único")
        if inimigo in _EARLY_LANE_PHYSICAL and modo == "SUP":
            adicionar("Ghost Scepter", 88, f"lane contra {inimigo}: proteção temporária contra ataques físicos")
            adicionar("Force Staff", 83, f"lane contra {inimigo}: reposicionamento para sair do alcance")
        if inimigo in _EARLY_LANE_SUSTAIN:
            if modo == "SUP":
                adicionar("Spirit Vessel", 82, f"jogo contra {inimigo}: reduzir cura/regeneração")
            elif modo == "MID":
                adicionar("Spirit Vessel", 81, f"jogo contra {inimigo}: reduzir cura/regeneração")
        if inimigo in _EARLY_LANE_INVIS:
            adicionar("Dust of Appearance", 90, f"lane contra {inimigo}: revelar invisibilidade em uma rotação")

    for inimigo in alvos:
        eh_ameaca = inimigo == ameaca
        peso_base = 75 if eh_ameaca else 60
        perfil = _ITENS_ESPECIFICOS.get(inimigo, {}).get(modo, [])
        if perfil:
            for idx, nome in enumerate(perfil):
                adicionar(nome, peso_base - idx, f"{inimigo} ({'ameaça do jogo' if eh_ameaca else 'inimigo de lane'}): counter específico para {modo}")
            continue
        tags = _TAGS_HEROIS.get(inimigo, set())
        for tag in tags:
            itens = _ITENS_POR_TAG_E_FUNCAO[modo].get(tag, [])
            for idx, nome in enumerate(itens[:4]):
                motivo = _TAGS_COUNTER.get(tag, {}).get(nome, f"resposta situacional ao perfil de {inimigo}")
                adicionar(nome, peso_base - idx - (0 if eh_ameaca else 8), f"{inimigo}: {motivo}")

    # Ordena por prioridade mais alta, preserva os primeiros itens dentro do tipo
    # de função e mantém a área Opções enxuta para caber na HUD.
    itens = [nome for nome, _ in sorted(ranking.items(), key=lambda par: (-par[1], par[0]))]
    # Não mostrar consumíveis de detecção quando não há invisível selecionado.
    if not any("invisible" in _TAGS_HEROIS.get(a, set()) for a in alvos) and not any(a in _EARLY_LANE_INVIS for a in lane_alvos):
        itens = [nome for nome in itens if nome not in {"Dust of Appearance", "Gem of True Sight"}]
    detalhes_unicos = []
    seen_details = set()
    for _, detalhe in sorted(detalhes, key=lambda par: (-par[0], par[1])):
        if detalhe not in seen_details:
            seen_details.add(detalhe)
            detalhes_unicos.append(detalhe)
    return itens[:8], detalhes_unicos[:12]
