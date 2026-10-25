import logging
import queue
import threading

from assistente.aplicacao.configurar_integracao_gsi import (
    ConfigurarIntegracaoGSI,
    ConfirmacaoReparoGSI,
    EstadoConfiguracaoGSI,
    ResultadoConfiguracaoGSI,
)
from assistente.aplicacao.contratos import ConsultaCancelada

REGISTRO = logging.getLogger(__name__)


class ExecutorConfiguracaoGSI:
    """Um pedido por vez, sem I/O na thread gráfica nem gravação durante importação."""

    def __init__(self, caso_de_uso: ConfigurarIntegracaoGSI) -> None:
        self._caso_de_uso = caso_de_uso
        self._trava = threading.Lock()
        self._sinal = threading.Event()
        self._encerrado = threading.Event()
        self._ocupado = False
        self._pedido: tuple[bool, ConfirmacaoReparoGSI | None] = (False, None)
        self._resultados: queue.Queue[ResultadoConfiguracaoGSI] = queue.Queue(maxsize=1)
        self._trabalhador = threading.Thread(target=self._processar, name="configurar-gsi", daemon=True)
        self._trabalhador.start()

    def solicitar(self, configurar: bool = False, confirmacao: ConfirmacaoReparoGSI | None = None) -> bool:
        if confirmacao is not None and not configurar:
            raise ValueError("Uma confirmação de reparo exige uma solicitação de configuração.")
        with self._trava:
            if self._ocupado or self._encerrado.is_set():
                return False
            self.obter_resultados()
            self._ocupado = True
            self._pedido = (configurar, confirmacao)
            self._sinal.set()
            return True

    def obter_resultados(self) -> list[ResultadoConfiguracaoGSI]:
        try:
            return [self._resultados.get_nowait()]
        except queue.Empty:
            return []

    def _verificar_ativa(self) -> None:
        if self._encerrado.is_set():
            raise ConsultaCancelada("O assistente foi fechado durante a configuração GSI.")

    def _processar(self) -> None:
        while True:
            self._sinal.wait()
            with self._trava:
                if self._encerrado.is_set():
                    return
                configurar, confirmacao = self._pedido
                self._sinal.clear()
            try:
                resultado = (
                    self._caso_de_uso.executar(confirmacao, self._verificar_ativa)
                    if configurar else self._caso_de_uso.verificar()
                )
            except ConsultaCancelada:
                with self._trava:
                    self._ocupado = False
                continue
            except Exception:
                REGISTRO.exception("Falha inesperada na configuração GSI.")
                resultado = ResultadoConfiguracaoGSI(
                    EstadoConfiguracaoGSI.FALHA, erro="Erro inesperado. Consulte o registro do aplicativo.",
                )
            with self._trava:
                if not self._encerrado.is_set():
                    self._ocupado = False
                    self._resultados.put_nowait(resultado)

    def encerrar(self) -> None:
        with self._trava:
            self._encerrado.set()
            self.obter_resultados()
            self._sinal.set()
        self._trabalhador.join(timeout=2)
        if self._trabalhador.is_alive():
            REGISTRO.warning(
                "A descoberta GSI ainda está encerrando; nenhum resultado será entregue à interface.",
            )
