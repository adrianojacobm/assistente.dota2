from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from assistente.aplicacao.consultar_recomendacoes import ConsultaRecomendacoes, ResultadoConsulta
from assistente.aplicacao.contratos import (
    ArmazenamentoPreferencias,
    ConsultasEmSegundoPlano,
    PlataformaJanelas,
)
from assistente.aplicacao.processar_partida import ProcessarPartida
from assistente.dominio.catalogo import HEROIS_DISPONIVEIS, IDS_HEROIS
from assistente.dominio.modelos import Funcao
from assistente.dominio.partida import EVENTOS

from .formatacao import formatar_painel
from .sobreposicoes import (
    SobreposicaoBase,
    SobreposicaoBuild,
    SobreposicaoBuybacks,
    SobreposicaoEstatisticas,
    SobreposicaoTemporizadores,
)

REGISTRO = logging.getLogger(__name__)
NOMES_SOBREPOSICOES = {
    "timers": "Timers de mapa", "stats": "Estatísticas", "build": "Build",
    "bb_esquerda": "Buybacks esquerda", "bb_direita": "Buybacks direita",
}


class PainelPrincipal:
    def __init__(
        self, janela: tk.Tk, assistente: ProcessarPartida, consultas: ConsultasEmSegundoPlano,
        preferencias: ArmazenamentoPreferencias, plataforma: PlataformaJanelas,
        antecedencia_minima: int = 5, antecedencia_maxima: int = 55,
    ) -> None:
        self.janela, self.assistente = janela, assistente
        self.consultas, self.preferencias, self.plataforma = consultas, preferencias, plataforma
        self.antecedencia_minima, self.antecedencia_maxima = antecedencia_minima, antecedencia_maxima
        self._fechado = False
        self._agendamentos: set[str] = set()
        self._identificador_consulta = 0
        self._resultado_atual: ResultadoConsulta | None = None
        janela.title("Assistente Dota 2 — builds por função e matchup")
        janela.geometry("440x600")
        janela.configure(bg="#12141a")
        self.temporizadores = SobreposicaoTemporizadores(janela, plataforma)
        self.estatisticas = SobreposicaoEstatisticas(janela, plataforma)
        self.build = SobreposicaoBuild(janela, plataforma)
        self.buybacks_esquerda = SobreposicaoBuybacks(janela, 320, 40, assistente, 0, plataforma)
        self.buybacks_direita = SobreposicaoBuybacks(janela, 1250, 40, assistente, 5, plataforma)
        self.sobreposicoes: dict[str, SobreposicaoBase] = {
            "timers": self.temporizadores, "stats": self.estatisticas, "build": self.build,
            "bb_esquerda": self.buybacks_esquerda, "bb_direita": self.buybacks_direita,
        }
        self._preferencias_carregadas = preferencias.carregar()
        for chave, sobreposicao in self.sobreposicoes.items():
            posicao = self._preferencias_carregadas["posicoes"].get(chave)
            if posicao:
                sobreposicao.definir_posicao(posicao["x"], posicao["y"])
            sobreposicao.alternar_trava(True)
            sobreposicao.atualizar_visibilidade(False)
        self._montar_interface()
        janela.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        self._agendar(400, self._atualizar_interface)
        self._agendar(100, self._receber_resultados)
        self._agendar(800, self._consultar)

    def _agendar(self, atraso: int, executar: Callable[[], None]) -> None:
        if self._fechado:
            return

        def chamar() -> None:
            self._agendamentos.discard(identificador)
            if not self._fechado:
                executar()

        identificador = self.janela.after(atraso, chamar)
        self._agendamentos.add(identificador)

    def _montar_interface(self) -> None:
        self.rotulo_status = tk.Label(
            self.janela, text="⏳ AGUARDANDO DOTA...", fg="#f59e0b", bg="#1b1e26",
            font=("Segoe UI", 10, "bold"),
        )
        self.rotulo_status.pack(fill="x", padx=6, pady=6)
        estilo = ttk.Style()
        estilo.theme_use("default")
        estilo.configure("TNotebook", background="#12141a", borderwidth=0)
        estilo.configure("TNotebook.Tab", background="#272a36", foreground="white", padding=[10, 5])
        estilo.map("TNotebook.Tab", background=[("selected", "#2563eb")])
        abas = ttk.Notebook(self.janela)
        abas.pack(fill="both", expand=True, padx=6, pady=2)
        geral, voz = tk.Frame(abas, bg="#1b1e26"), tk.Frame(abas, bg="#1b1e26")
        abas.add(geral, text="Builds & Counter-Pick")
        abas.add(voz, text="Voz & Tempos")
        self._montar_geral(geral)
        self._montar_voz(voz)

    def _montar_geral(self, quadro: tk.Frame) -> None:
        linha_funcao = tk.Frame(quadro, bg="#1b1e26")
        linha_funcao.pack(fill="x", padx=10, pady=5)
        tk.Label(linha_funcao, text="Função:", bg="#1b1e26", fg="#fbbf24").pack(side="left", padx=(0, 8))
        self._funcoes_por_rotulo = {f"{funcao.rotulo} (Pos {funcao.posicao})": funcao for funcao in Funcao}
        self.cb_funcao = ttk.Combobox(linha_funcao, values=list(self._funcoes_por_rotulo), state="readonly")
        funcao_atual = Funcao.normalizar(self.assistente.obter_configuracao()["modo"])
        self.cb_funcao.set(f"{funcao_atual.rotulo} (Pos {funcao_atual.posicao})")
        self.cb_funcao.pack(side="left", fill="x", expand=True)
        self.cb_funcao.bind("<<ComboboxSelected>>", self._alterar_funcao)
        self.botao_trava = tk.Button(
            quadro, text="🔓 Destravar Overlays", bg="#374151", fg="white",
            command=self._alternar_travas,
        )
        self.botao_trava.pack(fill="x", padx=10, pady=6)
        visibilidade = tk.LabelFrame(quadro, text="Exibir overlays", bg="#1b1e26", fg="#d1d5db")
        visibilidade.pack(fill="x", padx=10)
        self.visibilidades: dict[str, tk.BooleanVar] = {}
        for indice, (chave, nome) in enumerate(NOMES_SOBREPOSICOES.items()):
            variavel = tk.BooleanVar(
                master=self.janela,
                value=self._preferencias_carregadas["visibilidade"].get(chave, True),
            )
            self.visibilidades[chave] = variavel
            tk.Checkbutton(
                visibilidade, text=nome, variable=variavel, bg="#1b1e26", fg="white",
                selectcolor="#12141a", command=self._salvar_preferencias,
            ).grid(row=indice // 3, column=indice % 3, sticky="w")
        adversarios = tk.Frame(quadro, bg="#1b1e26")
        adversarios.pack(fill="x", padx=10, pady=5)
        self.selecoes: dict[str, ttk.Combobox] = {}
        campos = (("heroi", "Seu Herói:"), ("ameaca", "Ameaça:"), ("lane1", "Lane 1:"), ("lane2", "Lane 2:"))
        for indice, (chave, rotulo) in enumerate(campos):
            linha, coluna = indice // 2, (indice % 2) * 2
            tk.Label(adversarios, text=rotulo, bg="#1b1e26", fg="white").grid(
                row=linha, column=coluna, sticky="w", pady=3,
            )
            caixa = ttk.Combobox(adversarios, values=HEROIS_DISPONIVEIS, state="readonly", width=16)
            caixa.set("Sven" if chave == "heroi" else "Nenhum")
            caixa.grid(row=linha, column=coluna + 1, padx=5, pady=3)
            caixa.bind("<<ComboboxSelected>>", lambda evento: self._consultar())
            self.selecoes[chave] = caixa
        tk.Button(
            quadro, text="🎯 Atualizar Build & Calcular Counter-Picks", bg="#059669",
            fg="white", command=self._consultar,
        ).pack(fill="x", padx=10, pady=8)
        self.resultado_texto = tk.Text(
            quadro, height=12, width=48, font=("Consolas", 8), bg="#0b0d13", fg="#4ade80",
            relief="flat", padx=6, pady=6, state="disabled",
        )
        self.resultado_texto.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    def _montar_voz(self, quadro: tk.Frame) -> None:
        tk.Label(quadro, text="🔊 Avisos de Voz Ativos:", bg="#1b1e26", fg="#fbbf24").pack(
            anchor="w", padx=10, pady=10,
        )
        botoes = tk.Frame(quadro, bg="#1b1e26")
        botoes.pack(fill="x", padx=10)
        configuracao = self.assistente.obter_configuracao()
        self.avisos_voz: dict[str, tk.BooleanVar] = {}
        for indice, evento in enumerate(EVENTOS):
            variavel = tk.BooleanVar(master=self.janela, value=configuracao["voz"][evento.chave])
            self.avisos_voz[evento.chave] = variavel
            tk.Checkbutton(
                botoes, text=evento.rotulo, variable=variavel, bg="#1b1e26", fg="white",
                selectcolor="#12141a", command=self._atualizar_configuracao,
            ).grid(row=indice // 3, column=indice % 3, sticky="w")
        tk.Label(quadro, text="⚙️ Antecedência (Segundos):", bg="#1b1e26", fg="#34d399").pack(
            anchor="w", padx=10, pady=(15, 5),
        )
        tempos = tk.Frame(quadro, bg="#1b1e26")
        tempos.pack(fill="x", padx=10)
        self.antecedencias: dict[str, tk.Spinbox] = {}
        for indice, evento in enumerate(evento for evento in EVENTOS if evento.ajustavel):
            bloco = tk.Frame(tempos, bg="#272a36", padx=4, pady=2)
            bloco.grid(row=indice // 3, column=indice % 3, padx=4, pady=2)
            tk.Label(bloco, text=evento.abrev, bg="#272a36", fg="white").pack(side="left")
            controle = tk.Spinbox(
                bloco, from_=self.antecedencia_minima, to=self.antecedencia_maxima,
                width=3, command=self._atualizar_configuracao,
            )
            controle.delete(0, "end")
            controle.insert(0, str(evento.antecedencia))
            controle.pack(side="right")
            controle.bind("<KeyRelease>", lambda evento: self._atualizar_configuracao())
            self.antecedencias[evento.chave] = controle

    def _atualizar_configuracao(self) -> None:
        configuracao = self.assistente.obter_configuracao()
        configuracao["voz"] = {chave: variavel.get() for chave, variavel in self.avisos_voz.items()}
        for chave, controle in self.antecedencias.items():
            try:
                valor = int(controle.get())
            except ValueError:
                continue  # Campo pode ficar vazio enquanto o usuário digita.
            if self.antecedencia_minima <= valor <= self.antecedencia_maxima:
                configuracao["antecedencias"][chave] = valor
        self.assistente.configurar(configuracao)

    def _alterar_funcao(self, evento: tk.Event) -> None:
        funcao = self._funcoes_por_rotulo[self.cb_funcao.get()]
        self.assistente.selecionar_funcao(funcao)
        configuracao = self.assistente.obter_configuracao()
        for chave, variavel in self.avisos_voz.items():
            variavel.set(configuracao["voz"][chave])
        self._atualizar_configuracao()
        self.assistente.voz.falar(f"Modo {funcao.rotulo} ativado")
        self._consultar()

    def _alternar_travas(self) -> None:
        travado = not self.sobreposicoes["timers"].travado
        for sobreposicao in self.sobreposicoes.values():
            sobreposicao.alternar_trava(travado)
        self.botao_trava.configure(
            text="🔓 Destravar Overlays" if travado else "🔒 Travar Overlays",
            bg="#374151" if travado else "#f59e0b",
        )
        self._salvar_preferencias()

    def _salvar_preferencias(self) -> None:
        self.preferencias.salvar({
            "posicoes": {
                chave: sobreposicao.obter_posicao() for chave, sobreposicao in self.sobreposicoes.items()
            },
            "visibilidade": {chave: variavel.get() for chave, variavel in self.visibilidades.items()},
        })

    def _consultar(self) -> None:
        if self._fechado:
            return
        consulta = ConsultaRecomendacoes(
            self.selecoes["heroi"].get(), self._funcoes_por_rotulo[self.cb_funcao.get()],
            tuple(dict.fromkeys(
                self.selecoes[chave].get() for chave in ("lane1", "lane2")
                if self.selecoes[chave].get() != "Nenhum"
            )),
            self.selecoes["ameaca"].get(),
        )
        self._identificador_consulta = self.consultas.solicitar(consulta)
        self._resultado_atual = None
        self.build.atualizar(ResultadoConsulta(consulta))
        self._escrever("Consultando recomendações…")

    def _receber_resultados(self) -> None:
        for identificador, resultado in self.consultas.obter_resultados():
            if identificador == self._identificador_consulta:
                self._resultado_atual = resultado
                self.build.atualizar(resultado)
                self._escrever(formatar_painel(resultado))
        self._agendar(100, self._receber_resultados)

    def _escrever(self, texto: str) -> None:
        self.resultado_texto.configure(state="normal")
        self.resultado_texto.delete("1.0", "end")
        self.resultado_texto.insert("1.0", texto)
        self.resultado_texto.configure(state="disabled")

    def _atualizar_interface(self) -> None:
        estado = self.assistente.estado.snapshot()
        configuracao = self.assistente.obter_configuracao()
        mostrar = not self.temporizadores.travado or (estado["em_partida"] and self.plataforma.em_foco())
        for chave, sobreposicao in self.sobreposicoes.items():
            sobreposicao.atualizar_visibilidade(self.visibilidades[chave].get() and mostrar)
        if estado["conectado"] and estado["em_partida"]:
            funcao = Funcao.normalizar(configuracao["modo"])
            self.rotulo_status.configure(
                text=f"🔥 AO VIVO | Herói: {estado['heroi']} ({funcao.rotulo})", fg="#10b981",
            )
            if estado["heroi"] in IDS_HEROIS and estado["heroi"] != self.selecoes["heroi"].get():
                self.selecoes["heroi"].set(estado["heroi"])
                self._consultar()
            benchmark = self._resultado_atual.benchmark if self._resultado_atual else None
            self.temporizadores.atualizar(estado, configuracao)
            self.estatisticas.atualizar(estado, benchmark, configuracao["modo"])
            self.buybacks_esquerda.atualizar(estado)
            self.buybacks_direita.atualizar(estado)
        else:
            self.rotulo_status.configure(text="⏳ AGUARDANDO PARTIDA...", fg="#f59e0b")
        self._agendar(400, self._atualizar_interface)

    def _ao_fechar(self) -> None:
        if self._fechado:
            return
        self._fechado = True
        self._salvar_preferencias()
        for identificador in tuple(self._agendamentos):
            try:
                self.janela.after_cancel(identificador)
            except tk.TclError:
                REGISTRO.debug("Agendamento já encerrado: %s", identificador)
        self._agendamentos.clear()
        self.consultas.encerrar()
        self.assistente.encerrar()
        self.janela.destroy()
