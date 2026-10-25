# -*- coding: utf-8 -*-
import ctypes
import json
import queue
import sys
import threading
import time
import requests
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# =====================================================================
# 1. CONFIGURAÇÕES E CONSTANTES
# =====================================================================
PORTA = 4000
SEM_SINAL_S = 90
ANTECEDENCIA_MIN = 5
ANTECEDENCIA_MAX = 55
HEADERS_API = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

HERO_IDS = {
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
    'Invoker': 74, 'Silencer': 75, 'Outworld Destroyer': 76, 'Lycan': 77, 'Brewmaster': 78, 'Shadow Demon': 79,
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
ID_PARA_HEROI = {v: k for k, v in HERO_IDS.items()}
TODOS_HEROIS = ["Nenhum"] + sorted(list(HERO_IDS.keys()))

# Lista negra absoluta para banir componentes soltos, ingredientes e meias-peças
COMPONENTES_SOLTOS = {
    "Ogre Axe", "Broadsword", "Blade of Alacrity", "Staff of Wizardry", "Robe of the Magi",
    "Gloves of Haste", "Quarterstaff", "Helm of Iron Will", "Javelin", "Demon Edge",
    "Mystic Staff", "Eaglesong", "Reaver", "Sacred Relic", "Hyperstone", "Ultimate Orb",
    "Vitality Booster", "Energy Booster", "Point Booster", "Platemail", "Chainmail",
    "Blades of Attack", "Belt of Strength", "Band of Elvenskin", "Ring of Health", "Void Stone",
    "Mithril Hammer", "Blitz Knuckles", "Fluffy Hat", "Sage's Mask", "Ring of Regen", "Boots of Elvenskin",
    "Crown", "Diadem", "Cornucopia", "Blight Stone", "Windlace", "Ring of Protection", "Iron Branch", "Gauntlets",
    "Slippers", "Mantle", "Circlet", "Recipe", "Tango", "Healing Salve", "Clarity", "Observer Ward", "Sentry Ward",
    "Morbid Mask", "Headdress", "Ring of Basilius", "Buckler", "Urn of Shadows"
}

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

def formatar_nome_heroi(nome_gsi):
    nome_gsi = nome_gsi.lower().strip()
    if nome_gsi in GSI_PARA_NOME:
        return GSI_PARA_NOME[nome_gsi]
    limpo = nome_gsi.replace("npc_dota_hero_", "").replace("_", " ").title()
    for h in TODOS_HEROIS:
        if limpo.lower() == h.lower():
            return h
    return limpo

def dota_ou_painel_em_foco():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd == 0:
            return False
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        t = buff.value.lower()
        return ("dota 2" in t) or ("assistente" in t) or ("python" in t)
    except:
        return False

# =====================================================================
# 2. MOTOR OPENDOTA COM VALIDAÇÃO ESTATÍSTICA REAL POR ROLE
# =====================================================================
ADAPTACAO_LANE = {
    "Bristleback": "Magic Stick", "Zeus": "Infused Raindrops", "Batrider": "Magic Stick",
    "Phantom Assassin": "Magic Stick", "Skywrath Mage": "Infused Raindrops", "Lina": "Infused Raindrops",
    "Lion": "Infused Raindrops", "Necrophos": "Infused Raindrops", "Huskar": "Wind Lace",
    "Leshrac": "Infused Raindrops", "Queen of Pain": "Infused Raindrops", "Invoker": "Infused Raindrops",
    "Templar Assassin": "Blight Stone", "Treant Protector": "Quelling Blade", "Nature's Prophet": "Quelling Blade"
}

ADAPTACAO_JOGO = {
    "Phantom Assassin": {"CARRY": "Monkey King Bar", "MID": "Monkey King Bar", "SUP": "Ghost Scepter"},
    "Bristleback": {"CARRY": "Silver Edge", "MID": "Silver Edge", "SUP": "Spirit Vessel"},
    "Necrophos": {"CARRY": "Nullifier", "MID": "Nullifier", "SUP": "Spirit Vessel"},
    "Huskar": {"CARRY": "Eye of Skadi", "MID": "Eye of Skadi", "SUP": "Spirit Vessel"},
    "Slardar": {"CARRY": "Manta Style", "MID": "Black King Bar", "SUP": "Force Staff"},
    "Axe": {"CARRY": "Satanic", "MID": "Shiva's Guard", "SUP": "Eul's Scepter"},
    "Lion": {"CARRY": "Black King Bar", "MID": "Black King Bar", "SUP": "Glimmer Cape"},
    "Shadow Shaman": {"CARRY": "Black King Bar", "MID": "Black King Bar", "SUP": "Force Staff"},
    "Medusa": {"CARRY": "Diffusal Blade", "MID": "Diffusal Blade", "SUP": "Solar Crest"},
    "Slark": {"CARRY": "Bloodthorn", "MID": "Abyssal Blade", "SUP": "Ghost Scepter"},
    "Sniper": {"CARRY": "Blink Dagger", "MID": "Dragon Lance", "SUP": "Glimmer Cape"},
    "Storm Spirit": {"CARRY": "Orchid", "MID": "Bloodthorn", "SUP": "Eul's Scepter"},
    "Anti-Mage": {"CARRY": "Orchid", "MID": "Abyssal Blade", "SUP": "Ghost Scepter"}
}

class MotorOpenDota:
    def __init__(self):
        self.itens_por_id = {}
        self.hero_stats_cache = {}
        self.cache_builds = {}
        self.cache_matchups = {}
        self.cache_benchmarks = {}
        threading.Thread(target=self._inicializar_catalogo, daemon=True).start()

    def _inicializar_catalogo(self):
        try:
            r_i = requests.get("https://api.opendota.com/api/constants/items", headers=HEADERS_API, timeout=6)
            if r_i.status_code == 200:
                for chave, val in r_i.json().items():
                    if isinstance(val, dict) and "id" in val and "dname" in val:
                        if not chave.startswith("recipe_"):
                            self.itens_por_id[int(val["id"])] = val["dname"]
        except Exception as e:
            print(f"[Catálogo] Erro: {e}")

        try:
            r_hs = requests.get("https://api.opendota.com/api/heroStats", headers=HEADERS_API, timeout=6)
            if r_hs.status_code == 200:
                for h in r_hs.json():
                    hid = h.get("id")
                    picks = h.get("7_pick", 0) + h.get("8_pick", 0) + h.get("pro_pick", 0)
                    wins = h.get("7_win", 0) + h.get("8_win", 0) + h.get("pro_win", 0)
                    wr_meta = (wins / picks) if picks > 0 else 0.50
                    self.hero_stats_cache[hid] = {
                        "wr": wr_meta,
                        "roles": h.get("roles", []),
                        "picks": picks
                    }
        except Exception as e:
            print(f"[HeroStats] Erro: {e}")

    def _processar_frequencia_itens(self, dict_stage, limite=5):
        if not dict_stage:
            return []
        total_jogos = sum(int(val) for val in dict_stage.values())
        if total_jogos == 0:
            total_jogos = 1

        ordenados = sorted(dict_stage.items(), key=lambda x: int(x[1]), reverse=True)
        itens_filtrados = []
        for item_id_str, count in ordenados:
            nome = self.itens_por_id.get(int(item_id_str))
            if nome and nome not in COMPONENTES_SOLTOS and nome not in [i[0] for i in itens_filtrados]:
                pct = (int(count) / total_jogos) * 100
                if pct >= 5.0:
                    itens_filtrados.append((nome, pct))
            if len(itens_filtrados) >= limite:
                break
        return itens_filtrados

    def obter_benchmarks_heroi(self, meu_heroi):
        hid = HERO_IDS.get(meu_heroi)
        if not hid:
            return None
        if hid in self.cache_benchmarks:
            return self.cache_benchmarks[hid]

        try:
            r = requests.get(f"https://api.opendota.com/api/benchmarks?hero_id={hid}", headers=HEADERS_API, timeout=5)
            if r.status_code == 200:
                res = r.json().get("result", {})
                def extrair_p80(lista):
                    for item in lista:
                        if item.get("percentile") == 0.8:
                            return float(item.get("value", 0))
                    return 0.0

                bench = {
                    "gpm": extrair_p80(res.get("gold_per_min", [])),
                    "xpm": extrair_p80(res.get("xp_per_min", [])),
                    "lh_min": extrair_p80(res.get("last_hits_per_min", [])),
                    "k_min": extrair_p80(res.get("kills_per_min", []))
                }
                if bench["gpm"] > 0:
                    self.cache_benchmarks[hid] = bench
                    return bench
        except:
            pass
        return None

    def obter_build_contextualizada(self, meu_heroi, modo, lane1, lane2, ameaca):
        if not self.itens_por_id:
            self._inicializar_catalogo()

        hid = HERO_IDS.get(meu_heroi)
        if modo == "MID":
            lane_role_param = 2
        elif modo == "CARRY":
            lane_role_param = 1
        else:
            lane_role_param = 3

        if not hid:
            return {
                "heroi": meu_heroi,
                "perfil": modo,
                "start": "Herói não encontrado",
                "core": "N/A"
            }

        cache_key = (hid, lane_role_param)
        if cache_key not in self.cache_builds:
            try:
                url = f"https://api.opendota.com/api/heroes/{hid}/itemPopularity?lane_role={lane_role_param}"
                r = requests.get(url, headers=HEADERS_API, timeout=5)
                if r.status_code == 200:
                    self.cache_builds[cache_key] = r.json()
            except Exception as e:
                print(f"[ItemPopularity Role] Erro: {e}")

        dados_pop = self.cache_builds.get(cache_key, {})

        # Validação estricta: se a API retornar vazio para esta role específica, avisa o usuário em vez de inventar dados
        tem_dados = dados_pop and (dados_pop.get("start_game_items") or dados_pop.get("mid_game_items") or dados_pop.get("late_game_items"))
        
        if not tem_dados:
            return {
                "heroi": meu_heroi,
                "perfil": modo,
                "start": f"❌ Sem dados de {meu_heroi} como {modo}",
                "core": f"Este herói não foi jogado nessa role nas databases recentes."
            }

        start_tuples = self._processar_frequencia_itens(dados_pop.get("start_game_items", {}), 3)
        early_tuples = self._processar_frequencia_itens(dados_pop.get("early_game_items", {}), 4)
        mid_tuples = self._processar_frequencia_itens(dados_pop.get("mid_game_items", {}), 5)
        late_tuples = self._processar_frequencia_itens(dados_pop.get("late_game_items", {}), 4)

        start_nomes = [i[0] for i in start_tuples]
        
        core_nomes = []
        for nome, pct in (early_tuples + mid_tuples + late_tuples):
            if nome not in core_nomes and nome not in start_nomes:
                core_nomes.append(nome)

        for adv_lane in [lane1, lane2]:
            if adv_lane in ADAPTACAO_LANE:
                item_lane = ADAPTACAO_LANE[adv_lane]
                if item_lane not in start_nomes and item_lane not in core_nomes:
                    start_nomes.append(item_lane)

        if ameaca in ADAPTACAO_JOGO:
            item_counter = ADAPTACAO_JOGO[ameaca].get(modo, ADAPTACAO_JOGO[ameaca].get("CARRY", ""))
            if item_counter and item_counter not in core_nomes:
                core_nomes.append(f"{item_counter} (vs {ameaca})")

        start_str = " ➔ ".join(start_nomes[:4]) if start_nomes else "Dados insuficientes"
        core_str = " ➔ ".join(core_nomes[:7]) if core_nomes else "Dados insuficientes"

        return {
            "heroi": meu_heroi,
            "perfil": modo,
            "start": start_str,
            "core": core_str
        }

    def calcular_counter_picks(self, lane1, lane2, ameaca, modo):
        alvos = [a for a in [lane1, lane2, ameaca] if a and a != "Nenhum"]
        if not alvos:
            return "Selecione pelo menos 1 inimigo acima para cruzar Matchups + Meta."

        placar = {}
        for inimigo in alvos:
            ini_id = HERO_IDS.get(inimigo)
            if not ini_id:
                continue

            if ini_id not in self.cache_matchups:
                try:
                    r = requests.get(f"https://api.opendota.com/api/heroes/{ini_id}/matchups", headers=HEADERS_API, timeout=5)
                    if r.status_code == 200:
                        self.cache_matchups[ini_id] = r.json()
                except:
                    pass

            matchups_ini = self.cache_matchups.get(ini_id, [])
            for m in matchups_ini:
                hid = m.get("hero_id")
                jogos = m.get("games_played", 0)
                vitorias_inimigo = m.get("wins", 0)
                if jogos >= 15 and hid in ID_PARA_HEROI:
                    wr_nosso_heroi = 1.0 - (vitorias_inimigo / jogos)
                    if hid not in placar:
                        placar[hid] = [0.0, 0.0, 0]
                    peso = 1.5 if inimigo == ameaca else 1.0
                    placar[hid][0] += (wr_nosso_heroi * peso)
                    placar[hid][1] += peso
                    placar[hid][2] += jogos

        if not placar:
            return "Sem dados suficientes retornados pela API do OpenDota."

        papel_desejado = "Support" if modo == "SUP" else "Carry"
        ranking = []

        for hid, (soma_wr, soma_pesos, total_jogos) in placar.items():
            info_meta = self.hero_stats_cache.get(hid, {"wr": 0.50, "roles": []})
            roles = info_meta.get("roles", [])
            if roles and (papel_desejado not in roles):
                continue

            wr_confronto = (soma_wr / soma_pesos) * 100
            wr_meta = info_meta.get("wr", 0.50) * 100
            score_final = (wr_confronto * 0.7) + (wr_meta * 0.3)
            ranking.append((ID_PARA_HEROI[hid], wr_confronto, wr_meta, total_jogos, score_final))

        ranking.sort(key=lambda x: x[4], reverse=True)
        top_picks = ranking[:6]

        linhas = [f"🎯 TOP PICKS ({modo}) - MATCHUP + META IMORTAL/PRO:"]
        for nome, wr_vs, wr_m, am, _ in top_picks:
            linhas.append(f"• {nome:<18} | VS: {wr_vs:4.1f}% | Meta: {wr_m:4.1f}% ({am} jgs)")
        return "\n".join(linhas)

motor_api = MotorOpenDota()

# =====================================================================
# 3. EVENTOS (TIMERS) E CÁLCULO DE METAS
# =====================================================================
@dataclass(frozen=True)
class Evento:
    chave: str
    rotulo: str
    abrev: str
    nome_hud: str
    fala: str
    primeiro: int
    intervalo: int
    antecedencia: int
    inicio: float = float("-inf")
    fim: float = float("inf")
    ajustavel: bool = True

EVENTOS = (
    Evento("stack", "Stack", "Stk:", "STACK", "Hora do stack", 120, 60, 20, inicio=60, fim=2100),
    Evento("pull", "Pull", "Pull:", "PULL", "Hora do pull", 78, 30, 10, inicio=60, fim=900),
    Evento("agua", "Runa", "Runa:", "RUNA", "Runa de água/power", 120, 120, 25),
    Evento("bounty", "Bounty", "Bnty:", "BOUNTY", "Runa de bounty", 0, 240, 25),
    Evento("lotus", "Lótus", "Lót:", "LÓTUS", "Hora da lótus", 180, 180, 20),
    Evento("sabedoria", "Sabedoria", "Sab:", "XP", "Santuário de sabedoria", 420, 420, 20),
    Evento("tormentor", "Tormentor", "Torm:", "", "Hora do tormentor", 1200, 0, 30),
    Evento("catapulta", "Catapulta", "Cat:", "", "Onda de catapulta", 300, 300, 10, fim=600, ajustavel=False)
)
EVENTOS_HUD = [e for e in EVENTOS if e.nome_hud]

def calcular_metas(tempo, bench=None, modo="CARRY"):
    if tempo <= 0:
        return {"lh": 0, "dn": 0, "gpm": 0, "xpm": 0, "k": 0, "d": 0, "a": 0}
    m = tempo / 60.0
    fator = 0.35 if modo == "SUP" else (0.90 if modo == "MID" else 1.0)
    if bench:
        lh_rate = bench.get("lh_min", 8.0) * (0.85 if modo == "MID" else (0.35 if modo == "SUP" else 1.0))
        fator_early = 0.72 if m < 10 else 1.0
        gpm_base = bench.get("gpm", 550) * (0.90 if modo == "MID" else (0.65 if modo == "SUP" else 1.0))
        xpm_base = bench.get("xpm", 650) * (1.10 if modo == "MID" else (0.80 if modo == "SUP" else 1.0))
        return {
            "lh": int(m * lh_rate * fator_early),
            "dn": int(m * (1.8 if modo == "MID" else 1.5)),
            "gpm": int(gpm_base * (0.75 if m < 12 else 1.0)),
            "xpm": int(xpm_base * (0.75 if m < 12 else 1.0)),
            "k": int(m * bench.get("k_min", 0.35) * (1.1 if modo == "MID" else (0.6 if modo == "SUP" else 1.0))),
            "d": int(m * 0.25),
            "a": int(m * (0.8 if modo == "MID" else (0.95 if modo == "SUP" else 0.60)))
        }
    return {
        "lh": int(m * 7.0 * fator), "dn": int(m * (1.8 if modo == "MID" else 1.5)),
        "gpm": int((350 + (m * 8)) * (0.9 if modo == "MID" else (0.7 if modo == "SUP" else 1.0))),
        "xpm": int((400 + (m * 10)) * (1.1 if modo == "MID" else 1.0)),
        "k": int(m * 0.4), "d": int(m * 0.25), "a": int(m * 0.7)
    }

# =====================================================================
# 4. VOZ E ESTADO
# =====================================================================
class Voz:
    def __init__(self):
        self.fila = queue.Queue()
        self.disponivel = True
        threading.Thread(target=self._worker, daemon=True).start()

    def falar(self, texto):
        if self.disponivel:
            self.fila.put(texto)

    def _worker(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Rate, speaker.Volume = 2, 100
            for v in speaker.GetVoices():
                if "portuguese" in v.GetDescription().lower() or "brasil" in v.GetDescription().lower():
                    speaker.Voice = v
                    break
            while True:
                texto = self.fila.get()
                if texto is None:
                    break
                speaker.Speak(texto)
        except:
            self.disponivel = False

class Estado:
    def __init__(self):
        self.lock = threading.Lock()
        self._d = {
            "conectado": False, "em_partida": False, "tempo": -999,
            "heroi": "Aguardando...", "lh": 0, "dn": 0, "gpm": 0,
            "xpm": 0, "k": 0, "d": 0, "a": 0, "ultimo_post": 0.0
        }

    def atualizar(self, **kw):
        with self.lock:
            self._d.update(kw)

    def snapshot(self):
        with self.lock:
            d = dict(self._d)
        d["sem_sinal"] = d["conectado"] and (time.time() - d["ultimo_post"] > SEM_SINAL_S)
        if d["sem_sinal"]:
            d["em_partida"] = False
        return d

# =====================================================================
# 5. OVERLAYS (AUTO-AJUSTÁVEIS E SEM SOBRAS)
# =====================================================================
def aplicar_click_through(hwnd, ativar):
    try:
        estilo = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        estilo |= 0x00080000 | 0x08000000
        if ativar:
            estilo |= 0x00000020
        else:
            estilo &= ~0x00000020
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, estilo)
    except:
        pass

class BaseOverlay:
    def __init__(self, root, pos_x, pos_y, click_through=True):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True, "-alpha", 0.85)
        self.win.geometry(f"+{pos_x}+{pos_y}")

        self.container = tk.Frame(self.win, bg="#0b0d13", highlightbackground="#f59e0b", highlightthickness=2)
        self.container.pack(fill="both", expand=True)

        self.travado = False
        self.click_through = click_through
        self.visivel = True
        self.win.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.win.bind("<B1-Motion>", self._arrastar)
        self.win.update_idletasks()

    def get_hwnd(self):
        hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
        return hwnd if hwnd != 0 else self.win.winfo_id()

    def _iniciar_arraste(self, e):
        if not self.travado:
            self.offset_x, self.offset_y = e.x, e.y

    def _arrastar(self, e):
        if not self.travado:
            self.win.geometry(f"+{self.win.winfo_x() + e.x - self.offset_x}+{self.win.winfo_y() + e.y - self.offset_y}")

    def alternar_trava(self, travado):
        self.travado = travado
        self.container.configure(
            highlightbackground="#1f2937" if travado else "#f59e0b",
            highlightthickness=1 if travado else 2
        )
        if self.click_through:
            self.win.after(50, lambda: aplicar_click_through(self.get_hwnd(), travado))

    def atualizar_visibilidade(self, mostrar):
        if mostrar != self.visivel:
            if mostrar:
                self.win.deiconify()
                if self.click_through and self.travado:
                    self.win.after(50, lambda: aplicar_click_through(self.get_hwnd(), True))
            else:
                self.win.withdraw()
            self.visivel = mostrar

class OverlayTimers(BaseOverlay):
    def __init__(self, root):
        super().__init__(root, 350, 65)
        self.labels = {}
        for ev in EVENTOS_HUD:
            bloco = tk.Frame(self.container, bg="#0b0d13", padx=4, pady=2)
            bloco.pack(side="left")
            lbl = tk.Label(bloco, text=f"{ev.nome_hud}: --", font=("Consolas", 9, "bold"), fg="#e5e7eb", bg="#0b0d13")
            lbl.pack()
            self.labels[ev.chave] = (bloco, lbl)

    def atualizar(self, snap, configs):
        t = snap["tempo"]
        for ev in EVENTOS_HUD:
            if t <= ev.primeiro:
                seg = ev.primeiro - t
            elif ev.intervalo == 0:
                seg = 0
            else:
                seg = (-(t - ev.primeiro)) % ev.intervalo

            bloco, lbl = self.labels[ev.chave]
            if t < 0 and ev.chave in ["stack", "pull"]:
                txt, bg, fg = "AGUARD", "#0b0d13", "#6b7280"
            else:
                txt = f"{seg}s" if seg < 60 else f"{seg//60}:{seg%60:02d}"
                ant = configs["antecedencias"].get(ev.chave, ev.antecedencia)
                if seg <= 8:
                    bg, fg = "#991b1b", "#fef08a"
                elif seg <= ant:
                    bg, fg = "#78350f", "#fde047"
                else:
                    bg, fg = "#0b0d13", "#e5e7eb"
            bloco.configure(bg=bg)
            lbl.configure(text=f"{ev.nome_hud} {txt}", bg=bg, fg=fg)

class OverlayStats(BaseOverlay):
    def __init__(self, root):
        super().__init__(root, 15, 120)
        f = tk.Frame(self.container, bg="#0b0d13")
        f.pack(padx=6, pady=4)
        self.lbls = {}
        for idx, chave in enumerate(["LH/DN", "GPM", "XPM", "K/D/A"]):
            lbl = tk.Label(f, text=f"{chave}: --", font=("Consolas", 9, "bold"), bg="#0b0d13", fg="#e5e7eb")
            lbl.grid(row=idx, column=0, sticky="w", pady=1)
            self.lbls[chave] = lbl

    def atualizar(self, snap, bench, modo):
        m = calcular_metas(snap["tempo"], bench, modo)
        def cor(at, mt):
            return "#4ade80" if at >= mt else "#f87171"

        self.lbls["LH/DN"].configure(text=f"LH/DN: {snap['lh']}/{snap['dn']} (M:{m['lh']}/{m['dn']})", fg=cor(snap["lh"], m["lh"]))
        self.lbls["GPM"].configure(text=f"GPM: {snap['gpm']} (M:{m['gpm']})", fg=cor(snap["gpm"], m["gpm"]))
        self.lbls["XPM"].configure(text=f"XPM: {snap['xpm']} (M:{m['xpm']})", fg=cor(snap["xpm"], m["xpm"]))
        kda_cor = "#4ade80" if (snap['k'] + snap['a']) >= snap['d'] else "#f87171"
        self.lbls["K/D/A"].configure(text=f"K/D/A: {snap['k']}/{snap['d']}/{snap['a']} (M:{m['k']}/{m['d']}/{m['a']})", fg=kda_cor)

class OverlayBuild(BaseOverlay):
    def __init__(self, root):
        super().__init__(root, 15, 225)
        self.lbl_titulo = tk.Label(self.container, text="📋 BUILD PRO (OPENDOTA)", font=("Segoe UI", 8, "bold"), fg="#fbbf24", bg="#0b0d13")
        self.lbl_titulo.pack(anchor="nw", padx=6, pady=(3, 1))
        self.lbl_texto = tk.Label(self.container, text="Carregando...", font=("Segoe UI", 9, "bold"), fg="#e5e7eb", bg="#0b0d13", justify="left", anchor="nw", wraplength=380)
        self.lbl_texto.pack(padx=6, pady=(1, 4))

    def atualizar(self, dados):
        if not dados:
            return
        self.lbl_titulo.configure(text=f"📋 BUILD PRO META ({dados.get('perfil', '')}): {dados.get('heroi', '').upper()}")
        txt = f"🟢 SAÍDA:\n{dados.get('start', '')}\n\n🔴 ORDEM CORE (PRO):\n{dados.get('core', '')}"
        self.lbl_texto.configure(text=txt)

class OverlayBuybacksBar(BaseOverlay):
    def __init__(self, root, pos_x, pos_y, assistente, offset):
        super().__init__(root, pos_x, pos_y, click_through=False)
        self.a, self.offset = assistente, offset
        f = tk.Frame(self.container, bg="#0b0d13")
        f.pack(padx=2, pady=1)
        self.botoes = []
        for i in range(5):
            idx = self.offset + i
            btn = tk.Button(f, text="RDY", font=("Consolas", 8, "bold"), bg="#166534", fg="white", relief="flat", width=5, command=lambda x=idx: self._registrar(x))
            btn.pack(side="left", padx=10, pady=1)
            self.botoes.append(btn)

    def _registrar(self, idx):
        self.a.bb_timers[idx] = self.a.estado.snapshot()["tempo"] + 480
        self.a.bb_avisados[idx] = False

    def atualizar(self, snap):
        t = snap["tempo"]
        for i in range(5):
            idx = self.offset + i
            restante = self.a.bb_timers[idx] - t
            if restante <= 0:
                self.botoes[i].configure(text="RDY", bg="#166534")
            else:
                m, s = divmod(restante, 60)
                self.botoes[i].configure(text=f"{m}:{s:02d}", bg="#991b1b")
                if restante == 30 and not self.a.bb_avisados[idx]:
                    ts = "Esquerda" if self.offset == 0 else "Direita"
                    self.a.voz.falar(f"Buyback da {ts} voltando em 30 segundos")
                    self.a.bb_avisados[idx] = True

# =====================================================================
# 6. APP E SERVIDOR GSI
# =====================================================================
class Assistente:
    def __init__(self):
        self.estado = Estado()
        self.voz = Voz()
        self.cfg = {
            "modo": "CARRY",
            "voz": {e.chave: True for e in EVENTOS},
            "antecedencias": {e.chave: e.antecedencia for e in EVENTOS if e.ajustavel}
        }
        self.ultimo_t_aviso = None
        self.bb_timers, self.bb_avisados = [0] * 10, [False] * 10

    def avaliar_voz(self, tempo):
        if self.ultimo_t_aviso is None or tempo < self.ultimo_t_aviso or (tempo - self.ultimo_t_aviso) > 5:
            segs = [tempo]
        else:
            segs = range(self.ultimo_t_aviso + 1, tempo + 1)
        self.ultimo_t_aviso = tempo
        for t in segs:
            frases = []
            for ev in EVENTOS:
                if self.cfg["voz"].get(ev.chave) and (ev.inicio <= t <= ev.fim):
                    s_rest = ev.primeiro - t if t <= ev.primeiro else (-(t - ev.primeiro)) % ev.intervalo if ev.intervalo != 0 else -1
                    if s_rest == self.cfg["antecedencias"].get(ev.chave, ev.antecedencia):
                        frases.append(ev.fala)
            if frases:
                self.voz.falar(", e ".join(frases))

    def processar_gsi(self, data):
        mapa, player = data.get("map"), data.get("player")
        estados_validos = {
            "DOTA_GAMERULES_STATE_PRE_GAME",
            "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "DOTA_GAMERULES_STATE_HERO_SELECTION",
            "DOTA_GAMERULES_STATE_STRATEGY_TIME"
        }
        if not mapa or not player or mapa.get("game_state", "") not in estados_validos:
            self.estado.atualizar(conectado=True, em_partida=False, ultimo_post=time.time())
            return
        heroi_cru = data.get("hero", {}).get("name", "")
        tempo = int(mapa.get("clock_time", 0))
        self.estado.atualizar(
            conectado=True, em_partida=True, ultimo_post=time.time(), tempo=tempo,
            lh=player.get("last_hits", 0), dn=player.get("denies", 0), gpm=player.get("gpm", 0),
            xpm=player.get("xpm", 0), k=player.get("kills", 0), d=player.get("deaths", 0),
            a=player.get("assists", 0), heroi=formatar_nome_heroi(heroi_cru)
        )
        self.avaliar_voz(tempo)

class DotaGSIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            assistente_global.processar_gsi(json.loads(self.rfile.read(length).decode("utf-8")))
            self.send_response(200)
            self.end_headers()
        except:
            pass

class PainelPrincipal:
    def __init__(self, root, assistente):
        self.root, self.a = root, assistente
        self.root.title("Assistente v19.1 (Role Independent Pro Builds)")
        self.root.geometry("440x600")
        self.root.configure(bg="#12141a")

        self.overlays = {
            "timers": OverlayTimers(root),
            "stats": OverlayStats(root),
            "build": OverlayBuild(root),
            "bb_esquerda": OverlayBuybacksBar(root, 320, 40, assistente, 0),
            "bb_direita": OverlayBuybacksBar(root, 1250, 40, assistente, 5)
        }
        self.bench_atual = None

        self._montar_ui()
        for ov in self.overlays.values():
            ov.alternar_trava(False)
        self.root.after(400, self._loop_interface)

    def _montar_ui(self):
        f_topo = tk.Frame(self.root, bg="#1b1e26", pady=6, padx=8)
        f_topo.pack(fill="x", padx=6, pady=6)
        self.lbl_status = tk.Label(f_topo, text="⏳ AGUARDANDO DOTA...", font=("Segoe UI", 10, "bold"), fg="#f59e0b", bg="#1b1e26")
        self.lbl_status.pack()

        estilo = ttk.Style()
        estilo.theme_use("default")
        estilo.configure("TNotebook", background="#12141a", borderwidth=0)
        estilo.configure("TNotebook.Tab", background="#272a36", foreground="white", font=("Segoe UI", 9, "bold"), padding=[10, 5])
        estilo.map("TNotebook.Tab", background=[("selected", "#2563eb")])

        self.abas = ttk.Notebook(self.root)
        self.abas.pack(fill="both", expand=True, padx=6, pady=2)

        self.aba_geral = tk.Frame(self.abas, bg="#1b1e26")
        self.aba_voz = tk.Frame(self.abas, bg="#1b1e26")
        self.abas.add(self.aba_geral, text="Builds & Counter-Pick")
        self.abas.add(self.aba_voz, text="Voz & Tempos")

        self._montar_aba_geral()
        self._montar_aba_voz()

    def _montar_aba_geral(self):
        f = self.aba_geral
        f_modo = tk.Frame(f, bg="#1b1e26")
        f_modo.pack(fill="x", padx=6, pady=4)
        
        self.btn_carry = tk.Button(f_modo, text="⚔️ CARRY", bg="#2563eb", fg="white", font=("Segoe UI", 8, "bold"), command=lambda: self._set_modo("CARRY"))
        self.btn_carry.pack(side="left", expand=True, fill="x", padx=1)
        
        self.btn_mid = tk.Button(f_modo, text="🔮 MID", bg="#272a36", fg="#9ca3af", font=("Segoe UI", 8, "bold"), command=lambda: self._set_modo("MID"))
        self.btn_mid.pack(side="left", expand=True, fill="x", padx=1)
        
        self.btn_sup = tk.Button(f_modo, text="⚡ SUP", bg="#272a36", fg="#9ca3af", font=("Segoe UI", 8, "bold"), command=lambda: self._set_modo("SUP"))
        self.btn_sup.pack(side="left", expand=True, fill="x", padx=1)

        self.btn_trava = tk.Button(f, text="🔒 Travar Overlays (Após Posicionar)", font=("Segoe UI", 9, "bold"), bg="#f59e0b", fg="black", command=self._alternar_travas)
        self.btn_trava.pack(fill="x", pady=6, padx=10)

        f_match = tk.Frame(f, bg="#1b1e26")
        f_match.pack(fill="x", padx=10, pady=(4, 0))

        tk.Label(f_match, text="Seu Herói:", bg="#1b1e26", fg="#60a5fa", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=3)
        self.cb_meu_heroi = ttk.Combobox(f_match, values=TODOS_HEROIS, state="readonly", width=16)
        self.cb_meu_heroi.set("Sven")
        self.cb_meu_heroi.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(f_match, text="Ameaça:", bg="#1b1e26", fg="#f87171", font=("Segoe UI", 8, "bold")).grid(row=0, column=2, sticky="w", pady=3)
        self.cb_ameaca = ttk.Combobox(f_match, values=TODOS_HEROIS, state="readonly", width=16)
        self.cb_ameaca.set("Nenhum")
        self.cb_ameaca.grid(row=0, column=3, padx=5, pady=3)

        tk.Label(f_match, text="Lane 1:", bg="#1b1e26", fg="white", font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=3)
        self.cb_lane1 = ttk.Combobox(f_match, values=TODOS_HEROIS, state="readonly", width=16)
        self.cb_lane1.set("Nenhum")
        self.cb_lane1.grid(row=1, column=1, padx=5, pady=3)

        tk.Label(f_match, text="Lane 2:", bg="#1b1e26", fg="white", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", pady=3)
        self.cb_lane2 = ttk.Combobox(f_match, values=TODOS_HEROIS, state="readonly", width=16)
        self.cb_lane2.set("Nenhum")
        self.cb_lane2.grid(row=1, column=3, padx=5, pady=3)

        # Respeita 100% a escolha manual do usuário, sem alterar a role automaticamente ao escolher o herói
        self.cb_meu_heroi.bind("<<ComboboxSelected>>", lambda e: self._atualizar_tudo_api())
        for cb in [self.cb_lane1, self.cb_lane2, self.cb_ameaca]:
            cb.bind("<<ComboboxSelected>>", lambda e: self._atualizar_tudo_api())

        btn_calc = tk.Button(f, text="🎯 Atualizar Build & Calcular Counter-Picks", bg="#059669", fg="white", font=("Segoe UI", 9, "bold"), command=self._atualizar_tudo_api)
        btn_calc.pack(fill="x", pady=8, padx=10)

        self.txt_resultado = tk.Text(f, height=10, width=48, font=("Consolas", 8), bg="#0b0d13", fg="#4ade80", relief="flat", padx=6, pady=6)
        self.txt_resultado.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self.root.after(800, self._atualizar_tudo_api)

    def _montar_aba_voz(self):
        f = self.aba_voz
        tk.Label(f, text="🔊 Avisos de Voz Ativos:", bg="#1b1e26", fg="#fbbf24", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        grid_v = tk.Frame(f, bg="#1b1e26")
        grid_v.pack(fill="x", padx=10, pady=5)
        self.chk_voz = {}
        for i, ev in enumerate(EVENTOS):
            var = tk.BooleanVar(value=True)
            self.chk_voz[ev.chave] = var
            tk.Checkbutton(grid_v, text=ev.rotulo, variable=var, bg="#1b1e26", fg="white", selectcolor="#12141a", command=self._atualizar_cfg).grid(row=i//3, column=i%3, sticky="w", padx=2, pady=2)

        tk.Label(f, text="⚙️ Antecedência (Segundos):", bg="#1b1e26", fg="#34d399", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(15, 0))
        grid_a = tk.Frame(f, bg="#1b1e26")
        grid_a.pack(fill="x", padx=10, pady=5)
        self.spins = {}
        for i, ev in enumerate([e for e in EVENTOS if e.ajustavel]):
            sub = tk.Frame(grid_a, bg="#272a36", padx=4, pady=2)
            sub.grid(row=i//3, column=i%3, padx=4, pady=2, sticky="nsew")
            tk.Label(sub, text=ev.abrev, font=("Segoe UI", 8, "bold"), fg="#d1d5db", bg="#272a36").pack(side="left")
            sp = tk.Spinbox(sub, from_=ANTECEDENCIA_MIN, to=ANTECEDENCIA_MAX, width=3, font=("Consolas", 9, "bold"), command=self._atualizar_cfg)
            sp.delete(0, "end")
            sp.insert(0, str(ev.antecedencia))
            sp.pack(side="right")
            sp.bind("<KeyRelease>", lambda e: self._atualizar_cfg())
            self.spins[ev.chave] = sp

    def _set_modo(self, modo, falar_voz=True):
        self.a.cfg["modo"] = modo
        if modo == "CARRY":
            self.btn_carry.configure(bg="#2563eb", fg="white")
            self.btn_mid.configure(bg="#272a36", fg="#9ca3af")
            self.btn_sup.configure(bg="#272a36", fg="#9ca3af")
            ativos = ["bounty", "catapulta"]
        elif modo == "MID":
            self.btn_carry.configure(bg="#272a36", fg="#9ca3af")
            self.btn_mid.configure(bg="#d97706", fg="white")
            self.btn_sup.configure(bg="#272a36", fg="#9ca3af")
            ativos = ["agua", "bounty", "lotus", "sabedoria"]
        else:
            self.btn_carry.configure(bg="#272a36", fg="#9ca3af")
            self.btn_mid.configure(bg="#272a36", fg="#9ca3af")
            self.btn_sup.configure(bg="#7c3aed", fg="white")
            ativos = ["stack", "pull", "agua", "bounty", "lotus", "sabedoria", "tormentor"]

        for ch, var in self.chk_voz.items():
            var.set(ch in ativos)
        self._atualizar_cfg()
        self._atualizar_tudo_api()
        if falar_voz:
            self.a.voz.falar(f"Modo {modo} ativado")

    def _atualizar_cfg(self):
        for ch, var in self.chk_voz.items():
            self.a.cfg["voz"][ch] = var.get()
        for ch, sp in self.spins.items():
            try:
                self.a.cfg["antecedencias"][ch] = int(sp.get())
            except:
                pass

    def _alternar_travas(self):
        travado = not self.overlays["timers"].travado
        for ov in self.overlays.values():
            ov.alternar_trava(travado)
        self.btn_trava.configure(
            text="🔓 Destravar Overlays" if travado else "🔒 Travar Overlays",
            bg="#374151" if travado else "#f59e0b",
            fg="white" if travado else "black"
        )

    def _atualizar_tudo_api(self):
        heroi = self.cb_meu_heroi.get()
        l1, l2, am = self.cb_lane1.get(), self.cb_lane2.get(), self.cb_ameaca.get()
        modo = self.a.cfg["modo"]
        threading.Thread(target=self._worker_api, args=(heroi, modo, l1, l2, am), daemon=True).start()

    def _worker_api(self, heroi, modo, l1, l2, am):
        dados_build = motor_api.obter_build_contextualizada(heroi, modo, l1, l2, am)
        self.bench_atual = motor_api.obter_benchmarks_heroi(heroi)
        texto_counters = motor_api.calcular_counter_picks(l1, l2, am, modo)

        resumo_app = (
            f"📋 BUILD PRO ({heroi} - Rota: {dados_build['perfil']}):\n"
            f"• Saída: {dados_build['start']}\n"
            f"• Core:  {dados_build['core']}\n"
            f"{'-'*44}\n"
            f"{texto_counters}"
        )

        self.root.after(0, lambda: self.overlays["build"].atualizar(dados_build))
        self.root.after(0, lambda: self._escrever_painel(resumo_app))

    def _escrever_painel(self, texto):
        self.txt_resultado.configure(state="normal")
        self.txt_resultado.delete("1.0", "end")
        self.txt_resultado.insert("1.0", texto)
        self.txt_resultado.configure(state="disabled")

    def _loop_interface(self):
        snap = self.a.estado.snapshot()
        focado = dota_ou_painel_em_foco()
        mostrar = (not self.overlays["timers"].travado) or (snap["em_partida"] and focado)
        for ov in self.overlays.values():
            ov.atualizar_visibilidade(mostrar)

        if snap["conectado"] and snap["em_partida"]:
            self.lbl_status.configure(text=f"🔥 AO VIVO | Herói: {snap['heroi']} ({self.a.cfg['modo']})", fg="#10b981")

            # Atualiza apenas o herói detectado pelo GSI, preservando inteiramente a role/modo escolhida pelo usuário
            if snap["heroi"] in HERO_IDS and snap["heroi"] != self.cb_meu_heroi.get():
                self.cb_meu_heroi.set(snap["heroi"])
                self._atualizar_tudo_api()

            self.overlays["timers"].atualizar(snap, self.a.cfg)
            self.overlays["stats"].atualizar(snap, self.bench_atual, self.a.cfg["modo"])
            self.overlays["bb_esquerda"].atualizar(snap)
            self.overlays["bb_direita"].atualizar(snap)
        else:
            self.lbl_status.configure(text="⏳ AGUARDANDO PARTIDA...", fg="#f59e0b")

        self.root.after(400, self._loop_interface)

if __name__ == "__main__":
    assistente_global = Assistente()
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), DotaGSIHandler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    root = tk.Tk()
    app = PainelPrincipal(root, assistente_global)
    root.mainloop()