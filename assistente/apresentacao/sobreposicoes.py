from __future__ import annotations

import tkinter as tk

from assistente.aplicacao.consultar_recomendacoes import ResultadoConsulta
from assistente.aplicacao.contratos import PlataformaJanelas, Posicao
from assistente.aplicacao.processar_partida import ConfiguracaoAvisos, ProcessarPartida
from assistente.dominio.modelos import Funcao
from assistente.dominio.partida import EVENTOS_HUD, InstantaneoPartida, calcular_metas, segundos_para_evento

from .formatacao import formatar_quantidades, rotulo_referencia


class SobreposicaoBase:
    def __init__(
        self, janela: tk.Tk, x: int, y: int, plataforma: PlataformaJanelas,
        clique_transparente: bool = True,
    ) -> None:
        self.janela = tk.Toplevel(janela)
        self.janela.overrideredirect(True)
        self.janela.attributes("-topmost", True, "-alpha", 0.66)
        self.definir_posicao(x, y)
        self.plataforma = plataforma
        self.clique_transparente = clique_transparente
        self.travado, self.visivel = True, True
        self.deslocamento_x = self.deslocamento_y = 0
        self.conteudo = tk.Frame(
            self.janela, bg="#0b0d13", highlightbackground="#1f2937", highlightthickness=1,
        )
        self.conteudo.pack(fill="both", expand=True)
        self.janela.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.janela.bind("<B1-Motion>", self._arrastar)
        self.janela.update_idletasks()

    def obter_posicao(self) -> Posicao:
        return {"x": self.janela.winfo_x(), "y": self.janela.winfo_y()}

    def definir_posicao(self, x: int, y: int) -> None:
        self.janela.geometry(f"{x:+d}{y:+d}")

    def _iniciar_arraste(self, evento: tk.Event) -> None:
        if not self.travado:
            self.deslocamento_x, self.deslocamento_y = evento.x, evento.y

    def _arrastar(self, evento: tk.Event) -> None:
        if not self.travado:
            self.definir_posicao(
                self.janela.winfo_x() + evento.x - self.deslocamento_x,
                self.janela.winfo_y() + evento.y - self.deslocamento_y,
            )

    def alternar_trava(self, travado: bool) -> None:
        self.travado = travado
        self.conteudo.configure(
            highlightbackground="#1f2937" if travado else "#f59e0b",
            highlightthickness=1 if travado else 2,
        )
        if self.clique_transparente:
            identificador = self.plataforma.identificar(self.janela.winfo_id())
            self.plataforma.aplicar_transparencia(identificador, travado)

    def atualizar_visibilidade(self, mostrar: bool) -> None:
        if mostrar == self.visivel:
            return
        if mostrar:
            self.janela.deiconify()
            self.alternar_trava(self.travado)
        else:
            self.janela.withdraw()
        self.visivel = mostrar


class SobreposicaoTemporizadores(SobreposicaoBase):
    def __init__(self, janela: tk.Tk, plataforma: PlataformaJanelas) -> None:
        super().__init__(janela, 350, 65, plataforma)
        self.rotulos: dict[str, tuple[tk.Frame, tk.Label]] = {}
        for evento in EVENTOS_HUD:
            bloco = tk.Frame(self.conteudo, bg="#0b0d13", padx=4, pady=2)
            bloco.pack(side="left")
            rotulo = tk.Label(
                bloco, text=f"{evento.nome_hud}: --", font=("Consolas", 9, "bold"),
                bg="#0b0d13", fg="#e5e7eb",
            )
            rotulo.pack()
            self.rotulos[evento.chave] = bloco, rotulo

    def atualizar(self, estado: InstantaneoPartida, configuracao: ConfiguracaoAvisos) -> None:
        tempo = estado["tempo"]
        for evento in EVENTOS_HUD:
            restante = max(0, segundos_para_evento(evento, tempo))
            if tempo < 0 and evento.chave in ("stack", "pull"):
                texto, fundo, frente = "AGUARD", "#0b0d13", "#6b7280"
            else:
                texto = f"{restante}s" if restante < 60 else f"{restante // 60}:{restante % 60:02d}"
                antecedencia = configuracao["antecedencias"].get(evento.chave, evento.antecedencia)
                if restante <= 8:
                    fundo, frente = "#991b1b", "#fef08a"
                elif restante <= antecedencia:
                    fundo, frente = "#78350f", "#fde047"
                else:
                    fundo, frente = "#0b0d13", "#e5e7eb"
            bloco, rotulo = self.rotulos[evento.chave]
            bloco.configure(bg=fundo)
            rotulo.configure(text=f"{evento.nome_hud} {texto}", bg=fundo, fg=frente)


class SobreposicaoEstatisticas(SobreposicaoBase):
    def __init__(self, janela: tk.Tk, plataforma: PlataformaJanelas) -> None:
        super().__init__(janela, 15, 120, plataforma)
        self.rotulos: dict[str, tk.Label] = {}
        for chave in ("LH/DN", "GPM", "XPM", "K/D/A"):
            rotulo = tk.Label(
                self.conteudo, text=f"{chave}: --", font=("Consolas", 9, "bold"),
                bg="#0b0d13", fg="#e5e7eb",
            )
            rotulo.pack(anchor="w", padx=6, pady=2)
            self.rotulos[chave] = rotulo

    def atualizar(self, estado: InstantaneoPartida, benchmark: dict[str, object] | None, modo: str) -> None:
        funcao = Funcao.normalizar(modo)
        metas = calcular_metas(estado["tempo"], benchmark, funcao.perfil_counter)
        referencia = rotulo_referencia(benchmark, ("lh_min", "dn_min"))
        textos = {
            "LH/DN": (
                f"{estado['lh']}/{estado['dn']} ({referencia}:{metas['lh']}/{metas['dn']})",
                estado["lh"] >= metas["lh"],
            ),
            "GPM": (
                f"{estado['gpm']} ({rotulo_referencia(benchmark, ('gpm',))}:{metas['gpm']})",
                estado["gpm"] >= metas["gpm"],
            ),
            "XPM": (
                f"{estado['xpm']} ({rotulo_referencia(benchmark, ('xpm',))}:{metas['xpm']})",
                estado["xpm"] >= metas["xpm"],
            ),
            "K/D/A": (
                f"{estado['k']}/{estado['d']}/{estado['a']} "
                f"(Estimativa:{metas['k']}/{metas['d']}/{metas['a']})",
                estado["k"] + estado["a"] >= estado["d"],
            ),
        }
        for chave, (texto, atingiu) in textos.items():
            self.rotulos[chave].configure(text=f"{chave}: {texto}", fg="#4ade80" if atingiu else "#f87171")


class SobreposicaoBuild(SobreposicaoBase):
    def __init__(self, janela: tk.Tk, plataforma: PlataformaJanelas) -> None:
        super().__init__(janela, 15, 225, plataforma)
        self.titulo = tk.Label(
            self.conteudo, text="📋 BUILD", font=("Segoe UI", 8, "bold"), fg="#fbbf24", bg="#0b0d13",
        )
        self.titulo.pack(anchor="nw", padx=6, pady=(3, 1))
        self.texto = tk.Label(
            self.conteudo, text="Carregando...", font=("Segoe UI", 9, "bold"),
            fg="#e5e7eb", bg="#0b0d13", justify="left", anchor="nw", wraplength=370,
        )
        self.texto.pack(padx=6, pady=(1, 4))

    def atualizar(self, resultado: ResultadoConsulta) -> None:
        consulta, build = resultado.consulta, resultado.build
        self.titulo.configure(text=f"📋 BUILD ({consulta.funcao.rotulo.upper()}): {consulta.heroi.upper()}")
        fases = (
            ("🟢 SAÍDA", formatar_quantidades(build.saida) if build else ()),
            ("🟡 EARLY", build.inicio if build else ()),
            ("🟠 MID", build.meio if build else ()),
            ("🔴 LATE", build.final if build else ()),
            ("⚔ OPÇÕES", resultado.opcoes),
        )
        self.texto.configure(text="\n".join(
            f"{rotulo}: {', '.join(nomes) if nomes else '—'}" for rotulo, nomes in fases
        ))


class SobreposicaoBuybacks(SobreposicaoBase):
    def __init__(
        self, janela: tk.Tk, x: int, y: int, assistente: ProcessarPartida,
        inicio: int, plataforma: PlataformaJanelas,
    ) -> None:
        super().__init__(janela, x, y, plataforma, clique_transparente=False)
        self.assistente, self.inicio = assistente, inicio
        self.botoes = []
        for indice in range(inicio, inicio + 5):
            botao = tk.Button(
                self.conteudo, text="RDY", font=("Consolas", 8, "bold"), bg="#166534", fg="white",
                relief="flat", width=5, command=lambda valor=indice: self.assistente.registrar_buyback(valor),
            )
            botao.pack(side="left", padx=10, pady=1)
            self.botoes.append(botao)

    def atualizar(self, estado: InstantaneoPartida) -> None:
        restantes = self.assistente.atualizar_buybacks(estado["tempo"], self.inicio)
        for botao, restante in zip(self.botoes, restantes):
            minutos, segundos = divmod(restante, 60)
            botao.configure(
                text=f"{minutos}:{segundos:02d}" if restante else "RDY",
                bg="#991b1b" if restante else "#166534",
            )
