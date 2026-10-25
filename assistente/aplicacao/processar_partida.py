from collections import deque
from collections.abc import Callable
from threading import RLock
from typing import TypedDict

from assistente.dominio.modelos import Funcao
from assistente.dominio.partida import AVISOS_POR_FUNCAO, EVENTOS, AtualizacaoPartida, avaliar_eventos

from .contratos import EstadoPartida, SaidaVoz


class ConfiguracaoAvisos(TypedDict):
    modo: str
    voz: dict[str, bool]
    antecedencias: dict[str, int]


class ProcessarPartida:
    def __init__(self, estado: EstadoPartida, voz: SaidaVoz, relogio: Callable[[], float]) -> None:
        self.estado, self.voz = estado, voz
        self._relogio = relogio
        self._trava = RLock()
        self._encerrado = False
        self._identificador: str | None = None
        self._partidas_encerradas: deque[str] = deque(maxlen=16)
        self.cfg: ConfiguracaoAvisos = {
            "modo": "CARRY", "voz": {evento.chave: True for evento in EVENTOS},
            "antecedencias": {evento.chave: evento.antecedencia for evento in EVENTOS if evento.ajustavel},
        }
        self.ultimo_t_aviso: int | None = None
        self.bb_timers, self.bb_avisados = [0] * 10, [False] * 10

    def obter_configuracao(self) -> ConfiguracaoAvisos:
        with self._trava:
            return {
                "modo": self.cfg["modo"], "voz": self.cfg["voz"].copy(),
                "antecedencias": self.cfg["antecedencias"].copy(),
            }

    def configurar(self, configuracao: ConfiguracaoAvisos) -> None:
        if any(valor < 0 for valor in configuracao["antecedencias"].values()):
            raise ValueError("Antecedência não pode ser negativa.")
        with self._trava:
            self.cfg = {
                "modo": Funcao.normalizar(configuracao["modo"]).value,
                "voz": configuracao["voz"].copy(),
                "antecedencias": configuracao["antecedencias"].copy(),
            }

    def selecionar_funcao(self, funcao: Funcao) -> None:
        with self._trava:
            self.cfg["modo"] = funcao.value
            ativos = AVISOS_POR_FUNCAO[funcao.perfil_counter]
            self.cfg["voz"] = {evento.chave: evento.chave in ativos for evento in EVENTOS}

    def _reiniciar(self) -> None:
        self.ultimo_t_aviso = None
        self.bb_timers[:] = [0] * 10
        self.bb_avisados[:] = [False] * 10

    def processar(self, atualizacao: AtualizacaoPartida) -> None:
        with self._trava:
            if self._encerrado:
                return
            identificador = atualizacao.identificador
            if identificador and identificador in self._partidas_encerradas:
                return
            nova_partida = bool(identificador and identificador != self._identificador)
            anterior = self.estado.snapshot()
            if nova_partida:
                if self._identificador:
                    self._partidas_encerradas.append(self._identificador)
                self._identificador = identificador
                self._reiniciar()
            elif (identificador is None and self._identificador is None
                  and atualizacao.pre_jogo and atualizacao.tempo <= 0 < anterior["tempo"]):
                self._reiniciar()
            elif (atualizacao.em_partida and 0 <= atualizacao.tempo < anterior["tempo"]
                  and not atualizacao.pre_jogo):
                return
            if atualizacao.pre_jogo and atualizacao.tempo < 0 and anterior["tempo"] == 0:
                # Seleção de herói pode informar zero antes da contagem negativa.
                self.ultimo_t_aviso = None
            self.estado.aplicar(atualizacao, self._relogio())
            if atualizacao.em_partida:
                self.avaliar_voz(atualizacao.tempo)

    def avaliar_voz(self, tempo: int) -> None:
        with self._trava:
            anterior = self.ultimo_t_aviso
            if anterior is not None and tempo < anterior:
                return
            segundos = [tempo] if anterior is None or tempo - anterior > 5 else range(anterior + 1, tempo + 1)
            self.ultimo_t_aviso = tempo
            for segundo in segundos:
                frase = avaliar_eventos(segundo, self.cfg["voz"], self.cfg["antecedencias"])
                if frase:
                    self.voz.falar(frase)

    def registrar_buyback(self, indice: int) -> None:
        if not 0 <= indice < 10:
            raise ValueError("Índice de buyback inválido.")
        with self._trava:
            self.bb_timers[indice] = self.estado.snapshot()["tempo"] + 480
            self.bb_avisados[indice] = False

    def atualizar_buybacks(self, tempo: int, inicio: int) -> tuple[int, ...]:
        if inicio not in (0, 5):
            raise ValueError("Barra de buyback inválida.")
        with self._trava:
            restantes = tuple(
                max(0, self.bb_timers[indice] - tempo) if self.bb_timers[indice] else 0
                for indice in range(inicio, inicio + 5)
            )
            for indice, restante in enumerate(restantes, inicio):
                if self.bb_timers[indice] and 0 < restante <= 30 and not self.bb_avisados[indice]:
                    lado = "Esquerda" if inicio == 0 else "Direita"
                    self.voz.falar(f"Buyback da {lado} voltando em 30 segundos")
                    self.bb_avisados[indice] = True
            return restantes

    def encerrar(self) -> None:
        with self._trava:
            if self._encerrado:
                return
            self._encerrado = True
        self.voz.encerrar()
