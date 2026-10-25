import logging
import queue
import threading
from collections.abc import Callable

from assistente.aplicacao.consultar_recomendacoes import ConsultaRecomendacoes, ResultadoConsulta
from assistente.aplicacao.contratos import ConsultaCancelada

REGISTRO = logging.getLogger(__name__)


class ExecutorConsultas:
    """Uma consulta em execução, uma pendente substituível e um resultado recente."""

    def __init__(
        self, executar: Callable[[ConsultaRecomendacoes, Callable[[], None]], ResultadoConsulta],
    ) -> None:
        self._executar = executar
        self._condicao = threading.Condition()
        self._pendente: tuple[int, ConsultaRecomendacoes] | None = None
        self._resultados: queue.Queue[tuple[int, ResultadoConsulta]] = queue.Queue(maxsize=1)
        self._identificador = 0
        self._encerrado = False
        self._trabalhador = threading.Thread(target=self._processar, name="consultas-dota", daemon=True)
        self._trabalhador.start()

    def solicitar(self, consulta: ConsultaRecomendacoes) -> int:
        with self._condicao:
            if self._encerrado:
                raise RuntimeError("O executor já foi encerrado.")
            self._identificador += 1
            self._pendente = self._identificador, consulta
            self._condicao.notify()
            return self._identificador

    def obter_resultados(self) -> list[tuple[int, ResultadoConsulta]]:
        try:
            return [self._resultados.get_nowait()]
        except queue.Empty:
            return []

    def encerrar(self) -> None:
        with self._condicao:
            self._encerrado = True
            self._pendente = None
            self.obter_resultados()
            self._condicao.notify()
        self._trabalhador.join(timeout=0.2)

    def _verificar_ativa(self, identificador: int) -> None:
        with self._condicao:
            if self._encerrado or identificador != self._identificador:
                raise ConsultaCancelada()

    def _processar(self) -> None:
        while True:
            with self._condicao:
                self._condicao.wait_for(lambda: self._encerrado or self._pendente is not None)
                if self._encerrado:
                    return
                trabalho = self._pendente
                self._pendente = None
            if trabalho is None:
                continue
            identificador, consulta = trabalho
            try:
                resultado = self._executar(consulta, lambda: self._verificar_ativa(identificador))
            except ConsultaCancelada:
                continue
            except Exception:
                # Fronteira do trabalhador: mantém a GUI utilizável e registra o defeito.
                REGISTRO.exception("Falha inesperada ao atualizar recomendações.")
                resultado = ResultadoConsulta(
                    consulta,
                    erro_build="Erro inesperado ao atualizar os dados. Consulte o registro do aplicativo.",
                )
            with self._condicao:
                if not self._encerrado and identificador == self._identificador:
                    try:
                        self._resultados.get_nowait()
                    except queue.Empty:
                        pass
                    self._resultados.put_nowait((identificador, resultado))
