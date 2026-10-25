"""Heurísticas contextuais; não alteram a build estatística principal."""

from collections.abc import Sequence

from .modelos import Funcao


# Heurísticas de itens situacionais para a secção Opções. A build core nunca é
# alterada por estas regras: são sugestões independentes, filtradas pela função.
MOTIVOS_POR_PERFIL = {
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

ITENS_POR_PERFIL_E_FUNCAO = {
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
ITENS_POR_PERFIL_E_FUNCAO["OFFLANE"] = {
    perfil: list(itens) for perfil, itens in ITENS_POR_PERFIL_E_FUNCAO["MID"].items()
}
ITENS_POR_PERFIL_E_FUNCAO["OFFLANE"]["physical"] = ["Heaven's Halberd", "Shiva's Guard", "Ghost Scepter"]

PERFIS_HEROIS = {
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
ITENS_ESPECIFICOS = {
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

ADVERSARIOS_MAGICOS = {
    "Zeus", "Lina", "Skywrath Mage", "Pugna", "Leshrac", "Tinker", "Necrophos",
    "Batrider", "Jakiro", "Venomancer", "Invoker", "Queen of Pain", "Shadow Fiend",
}
ADVERSARIOS_FISICOS = {
    "Phantom Assassin", "Ursa", "Troll Warlord", "Sven", "Juggernaut", "Drow Ranger",
    "Slardar", "Wraith King", "Clinkz", "Legion Commander", "Riki",
}
ADVERSARIOS_SUSTENTACAO = {
    "Huskar", "Bristleback", "Necrophos", "Alchemist", "Morphling", "Abaddon", "Dazzle", "Oracle",
}
ADVERSARIOS_INVISIVEIS = {"Riki", "Clinkz", "Bounty Hunter", "Nyx Assassin", "Weaver"}


def recomendar_itens_counter(
    adversarios_lane: Sequence[str] = (), ameaca: str | None = None, modo: str = "CARRY",
) -> tuple[list[str], list[str]]:
    """Gera counters genéricos por inimigo, função e etapa (lane/jogo).

    Retorna (itens_para_overlay, explicações_para_painel). A build principal por
    frequência profissional não depende desta recomendação situacional.
    """
    modo = Funcao.normalizar(modo).perfil_counter
    adversarios_lane = list(dict.fromkeys(h for h in adversarios_lane if h and h != "Nenhum"))
    alvos = list(adversarios_lane)
    if ameaca and ameaca != "Nenhum" and ameaca not in alvos:
        alvos.append(ameaca)

    ranking: dict[str, int] = {}
    detalhes: list[tuple[int, str]] = []

    def adicionar(nome: str, peso: int, motivo: str) -> None:
        if not nome:
            return
        ranking[nome] = max(ranking.get(nome, 0), peso)
        detalhes.append((peso, f"{nome}: {motivo}"))

    for inimigo in adversarios_lane:
        # Lane: itens baratos de resposta imediata quando a habilidade do inimigo justifica.
        if inimigo in ADVERSARIOS_MAGICOS:
            adicionar("Magic Stick", 100, f"lane contra {inimigo}: cargas a partir de habilidades frequentes")
            adicionar(
                "Infused Raindrops", 95, f"lane contra {inimigo}: mitigação de dano mágico de alvo único",
            )
        if inimigo in ADVERSARIOS_FISICOS and modo == "SUP":
            adicionar(
                "Ghost Scepter", 88, f"lane contra {inimigo}: proteção temporária contra ataques físicos",
            )
            adicionar("Force Staff", 83, f"lane contra {inimigo}: reposicionamento para sair do alcance")
        if inimigo in ADVERSARIOS_SUSTENTACAO:
            if modo == "SUP":
                adicionar("Spirit Vessel", 82, f"jogo contra {inimigo}: reduzir cura/regeneração")
            elif modo == "MID":
                adicionar("Spirit Vessel", 81, f"jogo contra {inimigo}: reduzir cura/regeneração")
        if inimigo in ADVERSARIOS_INVISIVEIS:
            adicionar(
                "Dust of Appearance", 90, f"lane contra {inimigo}: revelar invisibilidade em uma rotação",
            )

    for inimigo in alvos:
        eh_ameaca = inimigo == ameaca
        peso_base = 75 if eh_ameaca else 60
        perfil = ITENS_ESPECIFICOS.get(inimigo, {}).get(modo, [])
        if perfil:
            for indice, nome in enumerate(perfil):
                contexto = "ameaça do jogo" if eh_ameaca else "inimigo de lane"
                adicionar(
                    nome, peso_base - indice, f"{inimigo} ({contexto}): counter específico para {modo}",
                )
            continue
        perfis = PERFIS_HEROIS.get(inimigo, set())
        for perfil_heroi in perfis:
            itens = ITENS_POR_PERFIL_E_FUNCAO[modo].get(perfil_heroi, [])
            for indice, nome in enumerate(itens[:4]):
                motivo = MOTIVOS_POR_PERFIL.get(perfil_heroi, {}).get(
                    nome, f"resposta situacional ao perfil de {inimigo}",
                )
                adicionar(nome, peso_base - indice - (0 if eh_ameaca else 8), f"{inimigo}: {motivo}")

    # Ordena por prioridade mais alta, preserva os primeiros itens dentro do tipo
    # de função e mantém a área Opções enxuta para caber na HUD.
    itens = [nome for nome, _ in sorted(ranking.items(), key=lambda par: (-par[1], par[0]))]
    # Não mostrar consumíveis de detecção quando não há invisível selecionado.
    if (not any("invisible" in PERFIS_HEROIS.get(alvo, set()) for alvo in alvos)
            and not any(alvo in ADVERSARIOS_INVISIVEIS for alvo in adversarios_lane)):
        itens = [nome for nome in itens if nome not in {"Dust of Appearance", "Gem of True Sight"}]
    detalhes_unicos = []
    detalhes_vistos = set()
    for _, detalhe in sorted(detalhes, key=lambda par: (-par[0], par[1])):
        if detalhe not in detalhes_vistos:
            detalhes_vistos.add(detalhe)
            detalhes_unicos.append(detalhe)
    return itens[:8], detalhes_unicos[:12]
