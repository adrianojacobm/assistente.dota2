# -*- coding: utf-8 -*-
"""
Ponto de entrada do Assistente de Dota 2.
Roda o servidor GSI (recebe dados ao vivo do jogo) e a interface Tkinter.
A lógica de build/counter-pick fica em build_engine.py e counter_engine.py —
este arquivo só orquestra: estado da partida, overlays e os cliques da UI.
"""
import ctypes
import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import build_engine
import counter_engine
import matchup_engine
import opendota_client as api
import config
from hero_data import HERO_IDS, TODOS_HEROIS, formatar_nome_heroi
from voz_eventos import EVENTOS, Voz, Estado
from overlays import OverlayTimers, OverlayStats, OverlayBuild, OverlayBuybacksBar

ARQUIVO_PREFERENCIAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preferencias_overlay.json")
POSICOES_PADRAO = {"timers": {"x": 350, "y": 65}, "stats": {"x": 15, "y": 120}, "build": {"x": 15, "y": 225}, "bb_esquerda": {"x": 320, "y": 40}, "bb_direita": {"x": 1250, "y": 40}}
NOMES_OVERLAYS = {"timers": "Timers de mapa", "stats": "Estatísticas", "build": "Build", "bb_esquerda": "Buybacks esquerda", "bb_direita": "Buybacks direita"}


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
    except Exception:
        return False


# =====================================================================
# ASSISTENTE (estado da partida + voz) e SERVIDOR GSI
# =====================================================================
class Assistente:
    def __init__(self):
        self.estado = Estado()
        self.voz = Voz()
        self.cfg = {
            "modo": "CARRY",
            "voz": {e.chave: True for e in EVENTOS},
            "antecedencias": {e.chave: e.antecedencia for e in EVENTOS if e.ajustavel},
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
                    s_rest = ev.primeiro - t if t <= ev.primeiro else ((-(t - ev.primeiro)) % ev.intervalo if ev.intervalo != 0 else -1)
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
            "DOTA_GAMERULES_STATE_STRATEGY_TIME",
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
            a=player.get("assists", 0), heroi=formatar_nome_heroi(heroi_cru),
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
        except Exception:
            pass


# =====================================================================
# PAINEL PRINCIPAL (Tkinter)
# =====================================================================
class PainelPrincipal:
    def __init__(self, root, assistente):
        self.root, self.a = root, assistente
        self.root.title("Assistente Dota 2 — builds por função e matchup")
        self.root.geometry("440x600")
        self.root.configure(bg="#12141a")

        self.preferencias = self._carregar_preferencias()
        pos = self.preferencias.get("posicoes", {})
        self.overlays = {
            "timers": OverlayTimers(root),
            "stats": OverlayStats(root),
            "build": OverlayBuild(root),
            "bb_esquerda": OverlayBuybacksBar(root, 320, 40, assistente, 0),
            "bb_direita": OverlayBuybacksBar(root, 1250, 40, assistente, 5),
        }
        for chave, ov in self.overlays.items():
            xy = pos.get(chave, POSICOES_PADRAO[chave])
            ov.definir_posicao(xy.get("x", POSICOES_PADRAO[chave]["x"]), xy.get("y", POSICOES_PADRAO[chave]["y"]))
            ov.alternar_trava(True)
            ov.ativado = bool(self.preferencias.get("visibilidade", {}).get(chave, True))
            if not ov.ativado:
                ov.atualizar_visibilidade(False)
        self.bench_atual = None
        self._api_request_id = 0
        self._dados_build_atual = None
        self._texto_counters_atual = ""

        self._montar_ui()
        self.btn_trava.configure(text="🔓 Destravar Overlays", bg="#374151", fg="white")
        self.root.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        self.root.after(400, self._loop_interface)

    def _carregar_preferencias(self):
        try:
            with open(ARQUIVO_PREFERENCIAS, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if not isinstance(dados, dict):
                return {"posicoes": {}, "visibilidade": {}}
            return dados
        except (OSError, json.JSONDecodeError):
            return {"posicoes": {}, "visibilidade": {}}

    def _salvar_preferencias(self):
        dados = {
            "posicoes": {chave: ov.obter_posicao() for chave, ov in self.overlays.items()},
            "visibilidade": {chave: bool(var.get()) for chave, var in getattr(self, "chk_overlays", {}).items()},
        }
        try:
            with open(ARQUIVO_PREFERENCIAS, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _ao_fechar(self):
        self._salvar_preferencias()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _alternar_visibilidade_overlay(self, chave):
        mostrar = bool(self.chk_overlays[chave].get())
        self.overlays[chave].atualizar_visibilidade(mostrar)
        self._salvar_preferencias()

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
        f_modo.pack(fill="x", padx=10, pady=5)
        tk.Label(f_modo, text="Função:", bg="#1b1e26", fg="#fbbf24", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        self._role_labels = {
            "CARRY": "Carry (Pos 1)", "MID": "Mid (Pos 2)",
            "OFFLANE": "Offlane (Pos 3)", "SUP": "Support (Pos 4)",
            "HARD_SUPPORT": "Hard Support (Pos 5)",
        }
        self._role_by_label = {label: role for role, label in self._role_labels.items()}
        self.cb_role = ttk.Combobox(f_modo, values=list(self._role_by_label), state="readonly", width=23)
        self.cb_role.set(self._role_labels.get(self.a.cfg.get("modo", "CARRY"), "Carry (Pos 1)"))
        self.cb_role.pack(side="left", fill="x", expand=True)
        self.cb_role.bind("<<ComboboxSelected>>", lambda e: self._set_modo(self._role_by_label.get(self.cb_role.get(), "CARRY")))

        self.btn_trava = tk.Button(f, text="🔒 Travar Overlays (Após Posicionar)", font=("Segoe UI", 9, "bold"), bg="#f59e0b", fg="black", command=self._alternar_travas)
        self.btn_trava.pack(fill="x", pady=6, padx=10)

        f_overlays = tk.LabelFrame(f, text="Exibir overlays", bg="#1b1e26", fg="#d1d5db", padx=5, pady=3)
        f_overlays.pack(fill="x", padx=10, pady=(0, 5))
        self.chk_overlays = {}
        for i, (chave, nome) in enumerate(NOMES_OVERLAYS.items()):
            var = tk.BooleanVar(value=bool(self.preferencias.get("visibilidade", {}).get(chave, True)))
            self.chk_overlays[chave] = var
            tk.Checkbutton(f_overlays, text=nome, variable=var, bg="#1b1e26", fg="white", selectcolor="#12141a", activebackground="#1b1e26", activeforeground="white", command=lambda k=chave: self._alternar_visibilidade_overlay(k)).grid(row=i // 3, column=i % 3, sticky="w", padx=3, pady=1)

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

        for cb in (self.cb_meu_heroi, self.cb_lane1, self.cb_lane2, self.cb_ameaca):
            cb.bind("<<ComboboxSelected>>", lambda e: self._atualizar_tudo_api())

        btn_calc = tk.Button(f, text="🎯 Atualizar Build & Calcular Counter-Picks", bg="#059669", fg="white", font=("Segoe UI", 9, "bold"), command=self._atualizar_tudo_api)
        btn_calc.pack(fill="x", pady=8, padx=10)

        self.txt_resultado = tk.Text(f, height=12, width=48, font=("Consolas", 8), bg="#0b0d13", fg="#4ade80", relief="flat", padx=6, pady=6)
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
            tk.Checkbutton(grid_v, text=ev.rotulo, variable=var, bg="#1b1e26", fg="white", selectcolor="#12141a", command=self._atualizar_cfg).grid(row=i // 3, column=i % 3, sticky="w", padx=2, pady=2)

        tk.Label(f, text="⚙️ Antecedência (Segundos):", bg="#1b1e26", fg="#34d399", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(15, 0))
        grid_a = tk.Frame(f, bg="#1b1e26")
        grid_a.pack(fill="x", padx=10, pady=5)
        self.spins = {}
        for i, ev in enumerate([e for e in EVENTOS if e.ajustavel]):
            sub = tk.Frame(grid_a, bg="#272a36", padx=4, pady=2)
            sub.grid(row=i // 3, column=i % 3, padx=4, pady=2, sticky="nsew")
            tk.Label(sub, text=ev.abrev, font=("Segoe UI", 8, "bold"), fg="#d1d5db", bg="#272a36").pack(side="left")
            sp = tk.Spinbox(sub, from_=config.ANTECEDENCIA_MIN, to=config.ANTECEDENCIA_MAX, width=3, font=("Consolas", 9, "bold"), command=self._atualizar_cfg)
            sp.delete(0, "end")
            sp.insert(0, str(ev.antecedencia))
            sp.pack(side="right")
            sp.bind("<KeyRelease>", lambda e: self._atualizar_cfg())
            self.spins[ev.chave] = sp

    def _set_modo(self, modo, falar_voz=True):
        valores_validos = {"CARRY", "MID", "OFFLANE", "SUP", "HARD_SUPPORT"}
        modo = modo if modo in valores_validos else "CARRY"
        self.a.cfg["modo"] = modo
        if hasattr(self, "cb_role"):
            self.cb_role.set(self._role_labels.get(modo, "Carry (Pos 1)"))
        if modo == "CARRY":
            ativos = ["bounty", "catapulta"]
        elif modo == "MID":
            ativos = ["agua", "bounty", "lotus", "sabedoria"]
        elif modo == "OFFLANE":
            ativos = ["bounty", "lotus", "sabedoria", "catapulta"]
        else:
            ativos = ["stack", "pull", "agua", "bounty", "lotus", "sabedoria", "tormentor"]

        for ch, var in self.chk_voz.items():
            var.set(ch in ativos)
        self._atualizar_cfg()
        self._atualizar_tudo_api()
        if falar_voz:
            self.a.voz.falar(f"Modo {self._role_labels.get(modo, modo)} ativado")

    def _atualizar_cfg(self):
        for ch, var in self.chk_voz.items():
            self.a.cfg["voz"][ch] = var.get()
        for ch, sp in self.spins.items():
            try:
                self.a.cfg["antecedencias"][ch] = int(sp.get())
            except Exception:
                pass

    def _alternar_travas(self):
        travado = not self.overlays["timers"].travado
        for ov in self.overlays.values():
            ov.alternar_trava(travado)
        self.btn_trava.configure(
            text="🔒 Travar Overlays" if travado else "🔓 Destravar Overlays",
            bg="#374151" if travado else "#f59e0b",
            fg="white" if travado else "black",
        )
        self._salvar_preferencias()

    def _atualizar_tudo_api(self):
        heroi = self.cb_meu_heroi.get()
        l1, l2, am = self.cb_lane1.get(), self.cb_lane2.get(), self.cb_ameaca.get()
        modo = self.a.cfg["modo"]
        self._api_request_id += 1
        request_id = self._api_request_id
        threading.Thread(
            target=self._worker_api,
            args=(heroi, modo, l1, l2, am, request_id),
            daemon=True,
        ).start()

    def _worker_api(self, heroi, modo, l1, l2, am, request_id):
        try:
            dados_build = build_engine.obter_build_contextualizada(heroi, modo, l1, l2, am, usar_agregado=False)
            hid = HERO_IDS.get(heroi)
            modo_stats = "SUP" if modo in ("SUP", "HARD_SUPPORT") else ("CARRY" if modo == "OFFLANE" else modo)
            bench = api.obter_benchmarks(hid, modo_stats) if hid else None
            catalogo_heroes = api.obter_catalogo_heroes()
            modo_counter = "SUP" if modo in ("SUP", "HARD_SUPPORT") else ("MID" if modo == "OFFLANE" else modo)
            texto_counters = counter_engine.calcular_counter_picks(l1, l2, am, modo_counter, catalogo_heroes)
            adversarios_lane = list(dict.fromkeys(h for h in (l1, l2) if h and h != "Nenhum"))
            opcoes, detalhes_opcoes = counter_engine.recomendar_itens_counter(
                lane_alvos=adversarios_lane, ameaca=am, modo=modo_counter
            )
            dados_build["opcoes"] = opcoes
            if detalhes_opcoes:
                dados_build["analise_matchup"] = "COUNTERS CONTEXTUAIS POR LANE/AMEAÇA:\n" + "\n".join(f"• {x}" for x in detalhes_opcoes)
            self.root.after(0, lambda: self._aplicar_resultados(request_id, dados_build, bench, texto_counters))
        except Exception as exc:
            mensagem = f"Erro ao atualizar os dados: {exc}"
            self.root.after(0, lambda: self._aplicar_erro_api(request_id, mensagem))

    def _worker_matchup(self, heroi, modo, adversarios, adversarios_lane, ameaca, request_id):
        try:
            resultado = matchup_engine.analisar_build_e_matchup(
                heroi, modo, adversarios, adversarios_lane, ameaca=ameaca
            )
        except Exception as exc:
            resultado = {"itens_funcao": {}, "amostra_funcao": 0,
                         "texto": f"Não foi possível analisar partidas dessa matchup: {exc}"}
        self.root.after(0, lambda: self._aplicar_analise_matchup(request_id, resultado))

    def _aplicar_resultados(self, request_id, dados_build, bench, texto_counters):
        # Se uma atualização mais recente já foi iniciada, descarta a resposta velha.
        if request_id != self._api_request_id:
            return
        self.bench_atual = bench
        self._dados_build_atual = dados_build
        self._texto_counters_atual = texto_counters
        adversarios = [h for h in (self.cb_lane1.get(), self.cb_lane2.get(), self.cb_ameaca.get()) if h and h != "Nenhum"]
        if not adversarios:
            self._dados_build_atual["analise_matchup"] = "Selecione adversário(s) para analisar partidas pro da mesma matchup."
        self.overlays["build"].atualizar(self._dados_build_atual)
        self._escrever_painel(self._formatar_resumo_app(self._dados_build_atual, self._texto_counters_atual))

    def _aplicar_analise_matchup(self, request_id, resultado):
        if request_id != self._api_request_id or not self._dados_build_atual:
            return
        amostra = int(resultado.get("amostra_funcao", 0) or 0)
        fases = resultado.get("itens_funcao", {}) or {}
        amostra_suficiente = amostra >= config.MIN_PARTIDAS_ROLE_BUILD
        if amostra_suficiente:
            self._dados_build_atual["fonte"] = "OpenDota /matches + purchase_log, filtrados por função"
            self._dados_build_atual["observacao"] = (
                f"Build por função calculada de {amostra} partidas profissionais parseadas (meta: últimas 100). "
                "A Saída considera compras de pré-jogo e respeita o teto de 600 ouro. "
                "Core inclui itens vistos em pelo menos 50% da amostra; itens abaixo disso ficam como situacionais. "
                "Counters em Opções são gerados separadamente pela ameaça e função, sem substituir a build core."
            )
        else:
            mensagem_sem_amostra = f"Sem amostra profissional suficiente para uma build exclusiva de {self._dados_build_atual.get('perfil', '')}."
            self._dados_build_atual["fonte"] = "OpenDota /matches: amostra por função insuficiente"
            self._dados_build_atual["observacao"] = (
                mensagem_sem_amostra + " Build principal ocultada para não misturar funções nem preencher com partidas não profissionais."
            )

        # Saída usa apenas compras de pré-jogo (timestamp <= 0), já validadas
        # pelo mecanismo principal contra o orçamento de 600 ouro. Quantidades
        # repetidas são exibidas com sufixo ×N.
        saida_base = list(fases.get("start", []) or []) if amostra_suficiente else []
        saida_lane = resultado.get("itens_saida_lane", []) or []
        saida_completa = list(dict.fromkeys(saida_base + saida_lane))

        # Deduplica entre fases; Magic Wand e outros itens não devem reaparecer
        # em outra fase se já estiverem no pacote inicial.
        itens_por_fase = {"start": saida_completa}
        for fase in ("early", "mid", "late"):
            itens_por_fase[fase] = list(fases.get(fase, []) or []) if amostra_suficiente else []
        itens_por_fase["early"].extend(resultado.get("itens_early_lane", []) or [])
        itens_por_fase = matchup_engine.deduplicar_fases(itens_por_fase)
        vistos = set()
        for fase in ("start", "early", "mid", "late"):
            self._dados_build_atual[fase] = " → ".join(itens_por_fase[fase])
            vistos.update(itens_por_fase[fase])
        if not self._dados_build_atual["start"]:
            self._dados_build_atual["start"] = "Sem amostra suficiente para saída por função/matchup." if not amostra_suficiente else ""

        # Opções são counters situacionais por função contra os inimigos escolhidos,
        # independentes da frequência da build core profissional.
        itens_core = vistos
        self._dados_build_atual["opcoes"] = [
            item for item in (resultado.get("opcoes", []) or []) if item not in itens_core
        ]
        self._dados_build_atual["core"] = "\n".join([
            f"EARLY: {self._dados_build_atual.get('early', '')}",
            f"MID: {self._dados_build_atual.get('mid', '')}",
            f"LATE: {self._dados_build_atual.get('late', '')}",
        ])
        self._dados_build_atual["analise_matchup"] = resultado.get("texto", "Sem análise de matchup.")
        self.overlays["build"].atualizar(self._dados_build_atual)
        self._escrever_painel(self._formatar_resumo_app(self._dados_build_atual, self._texto_counters_atual))

    @staticmethod
    def _formatar_resumo_app(dados_build, texto_counters):
        fases = (
            f"• Saída: {dados_build.get('start', '')}\n"
            f"• Early (0–10m): {dados_build.get('early', '')}\n"
            f"• Mid (10–25m): {dados_build.get('mid', '')}\n"
            f"• Late (25m+): {dados_build.get('late', '')}"
        )
        alertas = "\n".join(dados_build.get("alertas", []))
        observacao = dados_build.get("observacao", "")
        fonte = dados_build.get("fonte", "")
        analise_matchup = dados_build.get("analise_matchup", "")
        situacionais = dados_build.get("situacionais", []) or []
        bloco_situacionais = ("\nSituacionais D2PT (itens menos frequentes):\n" + "\n".join(f"• {x}" for x in situacionais[:18])) if situacionais else ""
        return (
            f"📋 BUILD ({dados_build.get('heroi', '')} - {dados_build.get('perfil', '')}):\n"
            f"{fases}\n"
            f"{alertas + chr(10) if alertas else ''}"
            f"{observacao + chr(10) if observacao else ''}"
            f"{('Fonte: ' + fonte) if fonte else ''}\n"
            f"{'-' * 44}\n"
            f"{analise_matchup}{bloco_situacionais}\n"
            f"{'-' * 44}\n"
            f"{texto_counters}"
        )

    def _aplicar_erro_api(self, request_id, mensagem):
        if request_id == self._api_request_id:
            self._escrever_painel(mensagem)

    def _escrever_painel(self, texto):
        self.txt_resultado.configure(state="normal")
        self.txt_resultado.delete("1.0", "end")
        self.txt_resultado.insert("1.0", texto)
        self.txt_resultado.configure(state="disabled")

    def _loop_interface(self):
        snap = self.a.estado.snapshot()
        focado = dota_ou_painel_em_foco()
        mostrar_contexto = (not self.overlays["timers"].travado) or (snap["em_partida"] and focado)
        for chave, ov in self.overlays.items():
            habilitado = self.chk_overlays[chave].get() if hasattr(self, "chk_overlays") else True
            ov.atualizar_visibilidade(bool(habilitado and mostrar_contexto))

        if snap["conectado"] and snap["em_partida"]:
            nome_funcao = getattr(self, "_role_labels", {}).get(self.a.cfg["modo"], self.a.cfg["modo"])
            self.lbl_status.configure(text=f"🔥 AO VIVO | Herói: {snap['heroi']} ({nome_funcao})", fg="#10b981")

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
    servidor = ThreadingHTTPServer(("127.0.0.1", config.PORTA_GSI), DotaGSIHandler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    root = tk.Tk()
    app = PainelPrincipal(root, assistente_global)
    root.mainloop()
