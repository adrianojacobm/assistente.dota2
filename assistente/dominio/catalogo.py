# -*- coding: utf-8 -*-
"""
Catálogo estático: IDs de heróis, mapa GSI->nome, lista de itens a ignorar.
Isto é só identificação/tradução de nomes — não tem estatística aqui dentro.
"""

IDS_HEROIS: dict[str, int] = {
    'Anti-Mage': 1, 'Axe': 2, 'Bane': 3, 'Bloodseeker': 4, 'Crystal Maiden': 5, 'Drow Ranger': 6,
    'Earthshaker': 7, 'Juggernaut': 8, 'Mirana': 9, 'Morphling': 10, 'Shadow Fiend': 11, 'Phantom Lancer': 12,
    'Puck': 13, 'Pudge': 14, 'Razor': 15, 'Sand King': 16, 'Storm Spirit': 17, 'Sven': 18, 'Tiny': 19,
    'Vengeful Spirit': 20, 'Windranger': 21, 'Zeus': 22, 'Kunkka': 23, 'Lina': 25, 'Lion': 26,
    'Shadow Shaman': 27, 'Slardar': 28, 'Tidehunter': 29, 'Witch Doctor': 30, 'Lich': 31, 'Riki': 32,
    'Enigma': 33, 'Tinker': 34, 'Sniper': 35, 'Necrophos': 36, 'Warlock': 37, 'Beastmaster': 38,
    'Queen of Pain': 39, 'Venomancer': 40, 'Faceless Void': 41, 'Wraith King': 42, 'Death Prophet': 43,
    'Phantom Assassin': 44, 'Pugna': 45, 'Templar Assassin': 46, 'Viper': 47, 'Luna': 48, 'Dragon Knight': 49,
    'Dazzle': 50, 'Clockwerk': 51, 'Leshrac': 52, "Nature's Prophet": 53, 'Lifestealer': 54, 'Dark Seer': 55,
    'Clinkz': 56, 'Omniknight': 57, 'Enchantress': 58, 'Huskar': 59, 'Night Stalker': 60, 'Broodmother': 61,
    'Bounty Hunter': 62, 'Weaver': 63, 'Jakiro': 64, 'Batrider': 65, 'Chen': 66, 'Spectre': 67,
    'Ancient Apparition': 68, 'Doom': 69, 'Ursa': 70, 'Spirit Breaker': 71, 'Gyrocopter': 72, 'Alchemist': 73,
    'Invoker': 74, 'Silencer': 75, 'Outworld Destroyer': 76, 'Lycan': 77,
    'Brewmaster': 78, 'Shadow Demon': 79,
    'Lone Druid': 80, 'Chaos Knight': 81, 'Meepo': 82, 'Treant Protector': 83, 'Ogre Magi': 84, 'Undying': 85,
    'Rubick': 86, 'Disruptor': 87, 'Nyx Assassin': 88, 'Naga Siren': 89, 'Keeper of the Light': 90, 'Io': 91,
    'Visage': 92, 'Slark': 93, 'Medusa': 94, 'Troll Warlord': 95, 'Centaur Warrunner': 96, 'Magnus': 97,
    'Timbersaw': 98, 'Bristleback': 99, 'Tusk': 100, 'Skywrath Mage': 101, 'Abaddon': 102, 'Elder Titan': 103,
    'Legion Commander': 104, 'Techies': 105, 'Ember Spirit': 106, 'Earth Spirit': 107, 'Underlord': 108,
    'Terrorblade': 109, 'Phoenix': 110, 'Oracle': 111, 'Winter Wyvern': 112, 'Arc Warden': 113,
    'Monkey King': 114, 'Pangolier': 119, 'Dark Willow': 120, 'Grimstroke': 121, 'Hoodwink': 123,
    'Void Spirit': 126, 'Snapfire': 128, 'Mars': 129, 'Dawnbreaker': 135, 'Marci': 136, 'Primal Beast': 137,
    'Muerta': 138, 'Kez': 145
}
HEROIS_POR_ID = {identificador: nome for nome, identificador in IDS_HEROIS.items()}
HEROIS_DISPONIVEIS = ["Nenhum"] + sorted(IDS_HEROIS)

GSI_PARA_NOME = {
    "npc_dota_hero_abyssal_underlord": "Underlord", "npc_dota_hero_anti_mage": "Anti-Mage",
    "npc_dota_hero_centaur": "Centaur Warrunner", "npc_dota_hero_doom_bringer": "Doom",
    "npc_dota_hero_furion": "Nature's Prophet", "npc_dota_hero_life_stealer": "Lifestealer",
    "npc_dota_hero_magnataur": "Magnus", "npc_dota_hero_necrolyte": "Necrophos",
    "npc_dota_hero_nevermore": "Shadow Fiend", "npc_dota_hero_obsidian_destroyer": "Outworld Destroyer",
    "npc_dota_hero_rattletrap": "Clockwerk", "npc_dota_hero_shredder": "Timbersaw",
    "npc_dota_hero_skeleton_king": "Wraith King", "npc_dota_hero_treant": "Treant Protector",
    "npc_dota_hero_windrunner": "Windranger", "npc_dota_hero_wisp": "Io", "npc_dota_hero_zuus": "Zeus"
}
GSI_PARA_NOME.update({
    "npc_dota_hero_antimage": "Anti-Mage",
    "npc_dota_hero_queenofpain": "Queen of Pain",
    "npc_dota_hero_vengefulspirit": "Vengeful Spirit",
})

# Componentes soltos: são ocultados nas fases após a saída; a lista inicial pode mostrá-los.
COMPONENTES_SOLTOS = {
    "Ogre Axe", "Broadsword", "Blade of Alacrity", "Staff of Wizardry", "Robe of the Magi",
    "Gloves of Haste", "Quarterstaff", "Helm of Iron Will", "Javelin", "Demon Edge",
    "Mystic Staff", "Eaglesong", "Reaver", "Sacred Relic", "Hyperstone", "Ultimate Orb",
    "Vitality Booster", "Energy Booster", "Point Booster", "Platemail", "Chainmail",
    "Blades of Attack", "Belt of Strength", "Band of Elvenskin", "Ring of Health", "Void Stone",
    "Mithril Hammer", "Blitz Knuckles", "Fluffy Hat", "Sage's Mask", "Ring of Regen", "Boots of Elvenskin",
    "Crown", "Diadem", "Cornucopia", "Blight Stone", "Windlace", "Ring of Protection", "Iron Branch",
    "Gauntlets", "Slippers", "Mantle", "Circlet", "Recipe", "Tango", "Healing Salve", "Clarity",
    "Observer Ward", "Sentry Ward",
    "Morbid Mask", "Headdress", "Ring of Basilius", "Buckler", "Urn of Shadows",
    "Mantle of Intelligence", "Oblivion Staff", "Sobi Mask", "Circlet of Nobility",
    "Wind Lace"
}


def formatar_nome_heroi(nome_gsi: str) -> str:
    """Converte o nome cru enviado pelo GSI do Dota 2 (ex: npc_dota_hero_antimage) no nome de exibição."""
    nome_gsi = (nome_gsi or "").lower().strip()
    if nome_gsi in GSI_PARA_NOME:
        return GSI_PARA_NOME[nome_gsi]
    limpo = nome_gsi.replace("npc_dota_hero_", "").replace("_", " ").title()
    for heroi in HEROIS_DISPONIVEIS:
        if limpo.lower() == heroi.lower():
            return heroi
    return limpo
