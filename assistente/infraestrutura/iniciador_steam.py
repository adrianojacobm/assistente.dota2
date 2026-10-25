import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from assistente.aplicacao.contratos import ErroInicializacao
from assistente.aplicacao.iniciar_dota import EstadoExecucao, ResultadoExecucao

from .steam import InstalacaoDota, validar_comando

REGISTRO = logging.getLogger(__name__)


class ErroInspecaoProcesso(RuntimeError):
    """O sistema não permitiu verificar o processo do jogo."""


class IniciadorSteam:
    """Ciclo de lançamento compartilhado; descoberta e inspeção são estratégias."""

    def __init__(
        self, localizar: Callable[[], InstalacaoDota], procurar_pid: Callable[[Path], int | None],
    ) -> None:
        self._localizar = localizar
        self._procurar_pid = procurar_pid
        self._instalacao: InstalacaoDota | None = None
        self._processo: subprocess.Popen[bytes] | None = None
        self._auxiliares: list[subprocess.Popen[bytes]] = []
        self._solicitado = False
        self._jogo_observado = False
        self._encerrado = False

    def localizar(self) -> InstalacaoDota:
        try:
            if self._instalacao is not None and self._instalacao.executavel.is_file():
                return self._instalacao
        except OSError as erro:
            REGISTRO.warning("Localização anterior do jogo inacessível; refazendo descoberta: %s", erro)
        self._instalacao = self._localizar()
        return self._instalacao

    def consultar(self) -> ResultadoExecucao:
        if self._encerrado:
            raise ErroInicializacao("O iniciador já foi encerrado.")
        instalacao = self.localizar()
        self._auxiliares = [processo for processo in self._auxiliares if processo.poll() is None]
        try:
            pid = self._procurar_pid(instalacao.executavel)
        except ErroInspecaoProcesso as erro:
            return self._resultado(EstadoExecucao.NAO_CONFIRMADO, erro=str(erro))
        if pid is not None:
            self._jogo_observado = True
            return self._resultado(EstadoExecucao.EM_EXECUCAO, pid_jogo=pid)
        if self._jogo_observado:
            self._jogo_observado = False
            self._solicitado = False
        if not self._solicitado or self._processo is None:
            return self._resultado(EstadoExecucao.NAO_OBSERVADO)
        codigo = self._processo.poll()
        if codigo is None:
            return self._resultado(EstadoExecucao.INICIADOR_ATIVO)
        if codigo != 0:
            self._solicitado = False
            return self._resultado(
                EstadoExecucao.FALHA, erro=f"O comando Steam encerrou com código {codigo}.",
            )
        return self._resultado(EstadoExecucao.SOLICITADO)

    def iniciar(self) -> ResultadoExecucao:
        atual = self.consultar()
        if atual.estado != EstadoExecucao.NAO_OBSERVADO:
            return atual
        instalacao = self.localizar()
        try:
            validar_comando(instalacao.comando_steam)
        except ErroInicializacao:
            self._instalacao = None
            raise
        try:
            self._processo = subprocess.Popen(
                [*instalacao.comando_steam, "-applaunch", "570"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                shell=False,
            )
        except PermissionError as erro:
            self._instalacao = None
            raise ErroInicializacao("Sem permissão para iniciar a Steam.") from erro
        except OSError as erro:
            self._instalacao = None
            raise ErroInicializacao(f"Não foi possível iniciar a Steam: {erro}") from erro
        self._auxiliares.append(self._processo)
        self._solicitado = True
        return self.consultar()

    def _resultado(
        self, estado: EstadoExecucao, pid_jogo: int | None = None, erro: str | None = None,
    ) -> ResultadoExecucao:
        return ResultadoExecucao(
            estado, pid_jogo=pid_jogo,
            pid_iniciador=(
                self._processo.pid
                if self._processo is not None and (self._solicitado or estado == EstadoExecucao.FALHA)
                else None
            ),
            executavel=str(self._instalacao.executavel) if self._instalacao else None, erro=erro,
        )

    def encerrar(self) -> None:
        self._encerrado = True
        for processo in self._auxiliares:
            # A Steam pode continuar ativa: apenas recolhemos os filhos já encerrados.
            if processo.poll() is None:
                REGISTRO.debug("Cliente Steam preservado (PID %s).", processo.pid)
        self._auxiliares.clear()
        self._processo = None
