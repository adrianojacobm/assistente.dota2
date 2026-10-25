from dataclasses import dataclass
from enum import Enum

from .contratos import ErroInicializacao, IniciadorDota


class EstadoExecucao(Enum):
    NAO_OBSERVADO = "nao_observado"
    SOLICITADO = "solicitado"
    INICIADOR_ATIVO = "iniciador_ativo"
    EM_EXECUCAO = "em_execucao"
    NAO_CONFIRMADO = "nao_confirmado"
    FALHA = "falha"


@dataclass(frozen=True)
class ResultadoExecucao:
    estado: EstadoExecucao
    pid_jogo: int | None = None
    pid_iniciador: int | None = None
    executavel: str | None = None
    erro: str | None = None

    def __post_init__(self) -> None:
        if any(pid is not None and pid <= 0 for pid in (self.pid_jogo, self.pid_iniciador)):
            raise ValueError("Identificador de processo deve ser positivo.")
        if self.estado == EstadoExecucao.EM_EXECUCAO and self.pid_jogo is None:
            raise ValueError("Processo do jogo não identificado.")
        if self.estado == EstadoExecucao.FALHA and not self.erro:
            raise ValueError("Uma falha precisa informar sua causa.")


class IniciarDota:
    def __init__(self, iniciador: IniciadorDota) -> None:
        self._iniciador = iniciador

    def consultar(self) -> ResultadoExecucao:
        try:
            return self._iniciador.consultar()
        except ErroInicializacao as erro:
            return ResultadoExecucao(EstadoExecucao.FALHA, erro=str(erro))

    def executar(self) -> ResultadoExecucao:
        atual = self.consultar()
        if atual.estado != EstadoExecucao.NAO_OBSERVADO:
            return atual
        try:
            return self._iniciador.iniciar()
        except ErroInicializacao as erro:
            return ResultadoExecucao(
                EstadoExecucao.FALHA, executavel=atual.executavel, erro=str(erro),
            )

    def encerrar(self) -> None:
        self._iniciador.encerrar()
